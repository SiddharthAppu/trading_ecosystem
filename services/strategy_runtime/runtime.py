from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from services.strategy_runtime.bootstrap import ensure_repo_paths

ensure_repo_paths()

from trading_core import get_adapter
from trading_core.analytics import compute_indicator_rows
from trading_core.auth import auth_manager
from trading_core.events import BarEvent
from trading_core.events import EventType, FillEvent, OrderEvent, TickEvent, bus
from trading_core.models import Bar, PositionSide, Side, Tick
from trading_core.strategies import Strategy, StrategyContext

from services.execution_engine.executor import PaperExecutor
from services.execution_engine.portfolio import PortfolioManager
from services.strategy_runtime.config import RuntimeSettings
from services.strategy_runtime.notifier import CompositeNotifier, NotificationMessage
from services.strategy_runtime.strategies import load_strategy, load_strategy_params

import websockets


logger = logging.getLogger("strategy_runtime.runtime")


@dataclass(slots=True)
class MarketSnapshot:
    symbol: str
    timeframe: str
    bar: Bar
    bars: list[Bar]
    indicators: dict[str, float | None]


@dataclass(slots=True)
class RiskDecision:
    accepted: bool
    reason: str = ""


class RuntimeRiskManager:
    def __init__(self, settings: RuntimeSettings):
        self.settings = settings
        self._trailing_peaks: dict[str, float] = {}

    def validate_entry(self, *, quantity: int, price: float, current_quantity: int) -> RiskDecision:
        if quantity <= 0:
            return RiskDecision(False, "quantity must be positive")
        if current_quantity + quantity > self.settings.max_position_quantity:
            return RiskDecision(False, "max_position_quantity breached")
        if quantity * price > self.settings.max_notional_per_trade:
            return RiskDecision(False, "max_notional_per_trade breached")
        return RiskDecision(True)

    def update_trailing_peak(self, symbol: str, price: float) -> None:
        peak = self._trailing_peaks.get(symbol)
        if peak is None or price > peak:
            self._trailing_peaks[symbol] = price

    def clear_symbol(self, symbol: str) -> None:
        self._trailing_peaks.pop(symbol, None)

    def evaluate_position_exit(self, symbol: str, side: PositionSide, avg_price: float, last_price: float) -> str | None:
        if side != PositionSide.LONG:
            return None

        stop_price = avg_price * (1 - self.settings.stop_loss_pct)
        if last_price <= stop_price:
            return "stop_loss"

        self.update_trailing_peak(symbol, last_price)
        trailing_peak = self._trailing_peaks.get(symbol, last_price)
        trailing_stop = trailing_peak * (1 - self.settings.trailing_stop_pct)
        if last_price <= trailing_stop:
            return "trailing_stop"

        return None


class BrokerPollingBarFeed:
    def __init__(self, settings: RuntimeSettings):
        self.settings = settings
        self.adapter = get_adapter(settings.provider)
        self._last_emitted_timestamp: datetime | None = None

    def _resolution(self) -> str:
        mapping = {"1m": "1", "5m": "5", "10m": "10"}
        return mapping.get(self.settings.timeframe, "1")

    def _normalize_candles(self, raw_candles: list[list]) -> list[Bar]:
        bars: list[Bar] = []
        for candle in raw_candles:
            if len(candle) < 6:
                continue
            timestamp = datetime.fromtimestamp(int(candle[0]))
            bars.append(
                Bar(
                    symbol=self.settings.symbol,
                    timestamp=timestamp,
                    open=float(candle[1]),
                    high=float(candle[2]),
                    low=float(candle[3]),
                    close=float(candle[4]),
                    volume=int(candle[5]),
                    timeframe=self.settings.timeframe,
                )
            )
        return bars

    async def fetch(self) -> list[Bar]:
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=5)
        raw_candles = await asyncio.to_thread(
            self.adapter.get_historical_data,
            self.settings.symbol,
            start_date.isoformat(),
            end_date.isoformat(),
            self._resolution(),
        )
        bars = self._normalize_candles(raw_candles)
        if not bars:
            return []

        recent_bars = bars[-self.settings.lookback_bars :]
        if self._last_emitted_timestamp is None:
            self._last_emitted_timestamp = recent_bars[-1].timestamp
            return recent_bars

        if recent_bars[-1].timestamp <= self._last_emitted_timestamp:
            return []

        self._last_emitted_timestamp = recent_bars[-1].timestamp
        return recent_bars


class ReplayWebSocketBarFeed:
    def __init__(self, settings: RuntimeSettings):
        self.settings = settings
        self._queue: asyncio.Queue[Bar] = asyncio.Queue()
        self._history: list[Bar] = []
        self._reader_task: asyncio.Task | None = None
        self._completed = False
        self._error: str = ""

    @property
    def completed(self) -> bool:
        return self._completed

    @property
    def error(self) -> str:
        return self._error

    async def _ensure_started(self) -> None:
        if self._reader_task and not self._reader_task.done():
            return
        self._reader_task = asyncio.create_task(self._read_stream())

    def _to_datetime(self, raw_time: str) -> datetime:
        normalized = str(raw_time).replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)

    def _row_to_bar(self, row: dict[str, Any]) -> Bar | None:
        if "time" not in row:
            return None
        timestamp = self._to_datetime(str(row["time"]))

        if all(key in row for key in ("open", "high", "low", "close")):
            return Bar(
                symbol=self.settings.symbol,
                timestamp=timestamp,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row.get("volume", 0) or 0),
                timeframe=self.settings.timeframe,
            )

        if "price" in row:
            price = float(row["price"])
            volume = int(row.get("volume", 0) or 0)
            return Bar(
                symbol=self.settings.symbol,
                timestamp=timestamp,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                timeframe=self.settings.timeframe,
            )

        return None

    async def _read_stream(self) -> None:
        config_payload: dict[str, Any] = {
            "symbol": self.settings.symbol,
            "provider": self.settings.provider,
            "data_type": self.settings.replay_data_type,
            "speed": self.settings.replay_speed,
            "timeframe": self.settings.timeframe,
            "indicators": self.settings.indicators,
        }
        if self.settings.replay_start_time:
            config_payload["start_time"] = self.settings.replay_start_time
        if self.settings.replay_end_time:
            config_payload["end_time"] = self.settings.replay_end_time

        try:
            async with websockets.connect(self.settings.replay_ws_url) as socket:
                await socket.send(json.dumps(config_payload))
                async for raw in socket:
                    data = json.loads(raw)
                    if "error" in data:
                        self._error = str(data["error"])
                        self._completed = True
                        break
                    if data.get("status") == "completed":
                        self._completed = True
                        break
                    if "status" in data:
                        continue

                    bar = self._row_to_bar(data)
                    if bar is None:
                        continue
                    self._history.append(bar)
                    if len(self._history) > self.settings.lookback_bars:
                        self._history = self._history[-self.settings.lookback_bars :]
                    await self._queue.put(bar)
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            self._completed = True

    async def fetch(self) -> list[Bar]:
        await self._ensure_started()

        if self._error:
            raise RuntimeError(f"Replay feed error: {self._error}")

        if self._completed and self._queue.empty():
            return []

        try:
            await asyncio.wait_for(self._queue.get(), timeout=5)
        except TimeoutError:
            if self._error:
                raise RuntimeError(f"Replay feed error: {self._error}")
            return []

        return self._history[-self.settings.lookback_bars :]


class StrategyRuntime:
    def __init__(self, settings: RuntimeSettings):
        self.settings = settings
        self.portfolio = PortfolioManager(initial_capital=settings.initial_capital)
        self.risk_manager = RuntimeRiskManager(settings)
        self.feed = self._build_feed(settings)
        self.notifier = CompositeNotifier.from_settings(settings)
        self._running = False
        self._started_at: datetime | None = None
        self._latest_error: str = ""
        self._latest_snapshot: MarketSnapshot | None = None
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=500)
        self.strategy = self._build_strategy()
        self._latest_price_by_symbol: dict[str, float] = {}
        self._wire_event_handlers()
        self.executor = PaperExecutor(initial_capital=settings.initial_capital)

    def _build_feed(self, settings: RuntimeSettings):
        if settings.feed_source == "replay_ws":
            return ReplayWebSocketBarFeed(settings)
        return BrokerPollingBarFeed(settings)

    def _build_strategy(self) -> Strategy:
        strategy_params = load_strategy_params(self.settings.strategy_name)
        strategy_params.update(
            {
                "quantity": self.settings.quantity,
                "provider": self.settings.provider,
                "timeframe": self.settings.timeframe,
            }
        )

        ctx = StrategyContext(
            bus,
            strategy_params,
            strategy_name=self.settings.strategy_name,
        )
        ctx.link_portfolio(self.portfolio)
        return load_strategy(ctx, self.settings.strategy_name, self.settings.strategy_class_path)

    def _record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._recent_events.append(
            {
                "time": datetime.utcnow().isoformat(),
                "type": event_type,
                "payload": payload,
            }
        )

    def _wire_event_handlers(self) -> None:
        bus.subscribe(EventType.BAR, self._on_bar_event)
        bus.subscribe(EventType.ORDER, self._on_order_event)
        bus.subscribe(EventType.FILL, self._on_fill_event)

    async def _on_bar_event(self, event: BarEvent) -> None:
        bar = event.bar
        if bar.symbol != self.settings.symbol:
            return
        self._record_event(
            "bar",
            {
                "symbol": bar.symbol,
                "timeframe": bar.timeframe,
                "time": bar.timestamp.isoformat(),
                "close": bar.close,
                "volume": bar.volume,
            },
        )

    async def _on_order_event(self, event: OrderEvent) -> None:
        order = event.order
        if order.symbol != self.settings.symbol:
            return

        self._record_event(
            "order",
            {
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "quantity": order.quantity,
                "price": order.price,
                "tag": order.tag,
            },
        )

        current_position = self.portfolio.get_position(order.symbol)
        current_quantity = current_position.quantity if current_position else 0
        reference_price = order.price or self._latest_price_by_symbol.get(order.symbol, 0.0)
        if reference_price <= 0 and current_position:
            reference_price = current_position.avg_price

        if order.side == Side.BUY and reference_price > 0:
            decision = self.risk_manager.validate_entry(
                quantity=order.quantity,
                price=reference_price,
                current_quantity=current_quantity,
            )
            if not decision.accepted:
                from trading_core.models import OrderStatus

                order.status = OrderStatus.REJECTED
                self.executor.orders.pop(order.order_id, None)
                logger.warning("Order rejected by runtime risk check: %s", decision.reason)
                self._record_event(
                    "risk_reject",
                    {
                        "order_id": order.order_id,
                        "symbol": order.symbol,
                        "reason": decision.reason,
                    },
                )
                await self.notifier.send(
                    NotificationMessage(
                        title="Risk rejection",
                        body=f"{order.symbol} {order.side} {order.quantity} rejected: {decision.reason}",
                        level="warning",
                    )
                )

    async def _on_fill_event(self, event: FillEvent) -> None:
        fill = event.fill
        if fill.symbol != self.settings.symbol:
            return

        self._record_event(
            "fill",
            {
                "order_id": fill.order_id,
                "symbol": fill.symbol,
                "side": fill.side.value,
                "quantity": fill.quantity,
                "price": fill.price,
                "filled_at": fill.filled_at.isoformat(),
            },
        )
        logger.info("Fill received: %s %s @ %s", fill.side, fill.quantity, fill.price)
        await self.notifier.send(
            NotificationMessage(
                title="Order filled",
                body=f"{fill.symbol} {fill.side} qty={fill.quantity} price={fill.price}",
                level="info",
            )
        )

        position = self.portfolio.get_position(fill.symbol)
        if position is None:
            self.risk_manager.clear_symbol(fill.symbol)
        elif position.side == PositionSide.LONG:
            self.risk_manager.update_trailing_peak(fill.symbol, fill.price)

    def _snapshot_from_bars(self, bars: list[Bar]) -> MarketSnapshot:
        rows = [
            {
                "time": bar.timestamp.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]
        compute_indicator_rows(rows, self.settings.indicators)
        latest = rows[-1]
        indicators = {
            key: latest.get(key)
            for key in ("ema_20", "sma_20", "rsi_14", "macd_line", "macd_signal", "macd_histogram")
            if key in latest
        }
        return MarketSnapshot(
            symbol=self.settings.symbol,
            timeframe=self.settings.timeframe,
            bar=bars[-1],
            bars=bars,
            indicators=indicators,
        )

    def get_status(self) -> dict[str, Any]:
        position = self.portfolio.get_position(self.settings.symbol)
        latest = self._latest_snapshot
        return {
            "running": self._running,
            "feed_source": self.settings.feed_source,
            "provider": self.settings.provider,
            "symbol": self.settings.symbol,
            "timeframe": self.settings.timeframe,
            "strategy": self.strategy.__class__.__name__,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_error": self._latest_error or None,
            "latest_bar": (
                {
                    "time": latest.bar.timestamp.isoformat(),
                    "open": latest.bar.open,
                    "high": latest.bar.high,
                    "low": latest.bar.low,
                    "close": latest.bar.close,
                    "volume": latest.bar.volume,
                }
                if latest
                else None
            ),
            "latest_indicators": latest.indicators if latest else None,
            "position": (
                {
                    "symbol": position.symbol,
                    "side": position.side.value,
                    "quantity": position.quantity,
                    "avg_price": position.avg_price,
                    "unrealized_pnl": position.unrealized_pnl,
                    "realized_pnl": position.realized_pnl,
                }
                if position
                else None
            ),
            "portfolio": {
                "cash": self.portfolio.cash,
                "equity": self.portfolio.equity,
            },
            "pending_orders": len(self.executor.orders),
            "replay": {
                "url": self.settings.replay_ws_url,
                "data_type": self.settings.replay_data_type,
                "speed": self.settings.replay_speed,
                "completed": getattr(self.feed, "completed", False),
                "error": getattr(self.feed, "error", "") or None,
            },
        }

    def get_recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return list(self._recent_events)[-limit:]

    async def _publish_market_event(self, bar: Bar) -> None:
        self._latest_price_by_symbol[bar.symbol] = bar.close
        await bus.publish(BarEvent(bar=bar))
        tick = Tick(symbol=bar.symbol, timestamp=bar.timestamp, price=bar.close, volume=bar.volume)
        await bus.publish(TickEvent(tick=tick))

    async def _apply_position_risk(self, snapshot: MarketSnapshot) -> None:
        position = self.portfolio.get_position(snapshot.symbol)
        if not position:
            self.risk_manager.clear_symbol(snapshot.symbol)
            return

        exit_reason = self.risk_manager.evaluate_position_exit(
            snapshot.symbol,
            position.side,
            position.avg_price,
            snapshot.bar.close,
        )
        if not exit_reason:
            return

        logger.warning("Risk exit triggered for %s: %s", snapshot.symbol, exit_reason)
        await self.strategy.ctx.sell(snapshot.symbol, position.quantity, tag=exit_reason)
        self._record_event(
            "risk_exit",
            {
                "symbol": snapshot.symbol,
                "reason": exit_reason,
                "price": snapshot.bar.close,
            },
        )
        await self.notifier.send(
            NotificationMessage(
                title="Risk exit",
                body=f"{snapshot.symbol} exited via {exit_reason} at {snapshot.bar.close}",
                level="warning",
            )
        )

    async def stop(self) -> None:
        self._running = False
        self.strategy.on_stop()
        await self.notifier.send(
            NotificationMessage(
                title="Strategy runtime stopped",
                body=f"provider={self.settings.provider} symbol={self.settings.symbol}",
                level="info",
            )
        )

    async def run(self) -> None:
        requires_auth = self.settings.feed_source != "replay_ws"
        if requires_auth and not auth_manager.is_authenticated(self.settings.provider):
            raise RuntimeError(f"Provider {self.settings.provider} is not authenticated")

        self._running = True
        self._started_at = datetime.utcnow()
        self._latest_error = ""
        self.strategy.on_init()
        self.strategy.on_start()
        self._record_event(
            "runtime_start",
            {
                "provider": self.settings.provider,
                "symbol": self.settings.symbol,
                "timeframe": self.settings.timeframe,
            },
        )
        await self.notifier.send(
            NotificationMessage(
                title="Strategy runtime started",
                body=f"provider={self.settings.provider} symbol={self.settings.symbol} timeframe={self.settings.timeframe}",
                level="info",
            )
        )

        try:
            while self._running:
                bars = await self.feed.fetch()
                if bars:
                    snapshot = self._snapshot_from_bars(bars)
                    self._latest_snapshot = snapshot
                    await self.strategy.evaluate_snapshot(snapshot)
                    await self._publish_market_event(snapshot.bar)
                    await self._apply_position_risk(snapshot)
                if self.settings.feed_source != "replay_ws":
                    await asyncio.sleep(self.settings.polling_interval_seconds)
                elif getattr(self.feed, "completed", False) and not bars:
                    logger.info("Replay feed completed; stopping runtime loop")
                    break
        except Exception as exc:
            self._latest_error = str(exc)
            self._record_event("runtime_error", {"error": str(exc)})
            await self.notifier.send(
                NotificationMessage(
                    title="Strategy runtime error",
                    body=str(exc),
                    level="warning",
                )
            )
            raise
        finally:
            self._running = False


def create_runtime(settings: RuntimeSettings) -> StrategyRuntime:
    return StrategyRuntime(settings)