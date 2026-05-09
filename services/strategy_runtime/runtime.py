from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path
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

from services.strategy_runtime.portfolio import PortfolioManager
from services.strategy_runtime.executor import PaperExecutor, LiveExecutor
from services.strategy_runtime.config import RuntimeSettings
from services.strategy_runtime.notifier import CompositeNotifier, NotificationMessage
from services.strategy_runtime.replay_option_data import ReplayOptionDataResolver
from services.strategy_runtime.strategies import load_strategy, load_strategy_params
from services.strategy_runtime.journal import JournalManager
from services.strategy_runtime.time_utils import isoformat_ist, now_ist

import websockets


logger = logging.getLogger("strategy_runtime.runtime")


def _timeframe_to_minutes(timeframe: str) -> int:
    mapping = {"1m": 1, "5m": 5, "10m": 10}
    return mapping.get(timeframe, 1)


def _bucket_start(timestamp: datetime, minutes: int) -> datetime:
    truncated = timestamp.replace(second=0, microsecond=0)
    bucket_minute = (truncated.minute // minutes) * minutes
    return truncated.replace(minute=bucket_minute)


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

    def validate_entry(
        self,
        *,
        quantity_units: int,
        lot_size: int,
        price: float,
        current_quantity_units: int,
    ) -> RiskDecision:
        if quantity_units <= 0:
            return RiskDecision(False, "quantity must be positive")
        if lot_size <= 0:
            return RiskDecision(False, "lot_size must be positive")
        if quantity_units % lot_size != 0:
            return RiskDecision(False, "quantity must be a whole multiple of lot_size")

        current_lots = current_quantity_units // lot_size
        new_lots = quantity_units // lot_size
        if current_lots + new_lots > self.settings.max_position_lots:
            return RiskDecision(False, "max_position_lots breached")
        if quantity_units * price > self.settings.max_notional_per_trade:
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


class TickToOneMinuteBarAggregator:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self._bucket_start: datetime | None = None
        self._open: float = 0.0
        self._high: float = 0.0
        self._low: float = 0.0
        self._close: float = 0.0
        self._volume: int = 0

    def _start_bucket(self, bucket_start: datetime, price: float, volume: int) -> None:
        self._bucket_start = bucket_start
        self._open = price
        self._high = price
        self._low = price
        self._close = price
        self._volume = volume

    def _to_bar(self) -> Bar | None:
        if self._bucket_start is None:
            return None
        return Bar(
            symbol=self.symbol,
            timestamp=self._bucket_start,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
            timeframe="1m",
        )

    def push_tick(self, timestamp: datetime, price: float, volume: int) -> list[Bar]:
        bucket = _bucket_start(timestamp, 1)
        if self._bucket_start is None:
            self._start_bucket(bucket, price, volume)
            return []

        if bucket == self._bucket_start:
            self._high = max(self._high, price)
            self._low = min(self._low, price)
            self._close = price
            self._volume += volume
            return []

        completed = self._to_bar()
        self._start_bucket(bucket, price, volume)
        return [completed] if completed else []

    def flush(self) -> list[Bar]:
        completed = self._to_bar()
        self._bucket_start = None
        self._open = 0.0
        self._high = 0.0
        self._low = 0.0
        self._close = 0.0
        self._volume = 0
        return [completed] if completed else []

    def current_bucket_start(self) -> datetime | None:
        return self._bucket_start


class BarTimeframeAggregator:
    def __init__(self, symbol: str, timeframe: str, minutes: int):
        self.symbol = symbol
        self.timeframe = timeframe
        self.minutes = minutes
        self._bucket_start: datetime | None = None
        self._open: float = 0.0
        self._high: float = 0.0
        self._low: float = 0.0
        self._close: float = 0.0
        self._volume: int = 0

    def _start_bucket(self, bucket_start: datetime, bar: Bar) -> None:
        self._bucket_start = bucket_start
        self._open = bar.open
        self._high = bar.high
        self._low = bar.low
        self._close = bar.close
        self._volume = bar.volume

    def _to_bar(self) -> Bar | None:
        if self._bucket_start is None:
            return None
        return Bar(
            symbol=self.symbol,
            timestamp=self._bucket_start,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
            timeframe=self.timeframe,
        )

    def push_bar(self, bar: Bar) -> list[Bar]:
        bucket = _bucket_start(bar.timestamp, self.minutes)
        if self._bucket_start is None:
            self._start_bucket(bucket, bar)
            return []

        if bucket == self._bucket_start:
            self._high = max(self._high, bar.high)
            self._low = min(self._low, bar.low)
            self._close = bar.close
            self._volume += bar.volume
            return []

        completed = self._to_bar()
        self._start_bucket(bucket, bar)
        return [completed] if completed else []

    def flush(self) -> list[Bar]:
        completed = self._to_bar()
        self._bucket_start = None
        self._open = 0.0
        self._high = 0.0
        self._low = 0.0
        self._close = 0.0
        self._volume = 0
        return [completed] if completed else []

    def current_bucket_start(self) -> datetime | None:
        return self._bucket_start


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
        self._target_minutes = _timeframe_to_minutes(self.settings.timeframe)
        self._aggregate_ticks_to_bars = (
            self.settings.replay_data_type == "market_ticks"
            and self.settings.indicator_input_mode == "bars_1m"
        )
        self._tick_to_one_min = TickToOneMinuteBarAggregator(self.settings.symbol) if self._aggregate_ticks_to_bars else None
        self._one_min_to_target = (
            BarTimeframeAggregator(self.settings.symbol, self.settings.timeframe, self._target_minutes)
            if self._aggregate_ticks_to_bars and self._target_minutes > 1
            else None
        )

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

    def _emit_bar(self, bar: Bar) -> None:
        self._history.append(bar)
        if len(self._history) > self.settings.lookback_bars:
            self._history = self._history[-self.settings.lookback_bars :]
        self._queue.put_nowait(bar)

    def _route_one_min_bar(self, one_min_bar: Bar) -> list[Bar]:
        if not self._one_min_to_target:
            one_min_bar.timeframe = self.settings.timeframe
            return [one_min_bar]
        return self._one_min_to_target.push_bar(one_min_bar)

    def _ingest_tick_row(self, row: dict[str, Any]) -> list[Bar]:
        if not self._tick_to_one_min:
            direct = self._row_to_bar(row)
            return [direct] if direct else []
        if "time" not in row or "price" not in row:
            return []
        timestamp = self._to_datetime(str(row["time"]))
        price = float(row["price"])
        volume = int(row.get("volume", 0) or 0)
        one_min_bars = self._tick_to_one_min.push_tick(timestamp, price, volume)
        out: list[Bar] = []
        for one_min in one_min_bars:
            out.extend(self._route_one_min_bar(one_min))
        return out

    def _flush_aggregators(self) -> list[Bar]:
        if not self._tick_to_one_min:
            return []
        out: list[Bar] = []
        for one_min in self._tick_to_one_min.flush():
            out.extend(self._route_one_min_bar(one_min))
        if self._one_min_to_target:
            out.extend(self._one_min_to_target.flush())
        return out

    async def _read_stream(self) -> None:
        requested_timeframe = (
            "1m" if self._aggregate_ticks_to_bars else self.settings.timeframe
        )
        config_payload: dict[str, Any] = {
            "symbol": self.settings.symbol,
            "provider": self.settings.provider,
            "data_type": self.settings.replay_data_type,
            "speed": self.settings.replay_speed,
            "timeframe": requested_timeframe,
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
                    if data.get("status") == "no_data":
                        self._completed = True
                        self._error = str(data.get("message") or "No replay data found")
                        break
                    if data.get("status") == "completed":
                        self._completed = True
                        break
                    if "status" in data:
                        continue
                    if self._aggregate_ticks_to_bars:
                        bars = self._ingest_tick_row(data)
                        for bar in bars:
                            self._emit_bar(bar)
                    else:
                        bar = self._row_to_bar(data)
                        if bar is None:
                            continue
                        self._emit_bar(bar)

                if self._aggregate_ticks_to_bars:
                    for bar in self._flush_aggregators():
                        self._emit_bar(bar)

                # If the socket closes normally without an explicit terminal status,
                # mark feed completed so the runtime loop can exit cleanly.
                if not self._completed:
                    self._completed = True
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            self._completed = True

    async def fetch(self) -> list[Bar]:
        await self._ensure_started()

        if self._completed and self._queue.empty():
            return []

        if self._error:
            raise RuntimeError(f"Replay feed error: {self._error}")

        try:
            await asyncio.wait_for(self._queue.get(), timeout=5)
        except TimeoutError:
            if self._error:
                raise RuntimeError(f"Replay feed error: {self._error}")
            return []

        return self._history[-self.settings.lookback_bars :]

    def get_aggregation_status(self) -> dict[str, Any]:
        return {
            "enabled": self._aggregate_ticks_to_bars,
            "indicator_input_mode": self.settings.indicator_input_mode,
            "source_data_type": self.settings.replay_data_type,
            "source_stream_timeframe": "1m" if self._aggregate_ticks_to_bars else self.settings.timeframe,
            "target_timeframe": self.settings.timeframe,
            "open_tick_bucket_start": (
                isoformat_ist(self._tick_to_one_min.current_bucket_start())
                if self._tick_to_one_min and self._tick_to_one_min.current_bucket_start()
                else None
            ),
            "open_target_bucket_start": (
                isoformat_ist(self._one_min_to_target.current_bucket_start())
                if self._one_min_to_target and self._one_min_to_target.current_bucket_start()
                else None
            ),
        }


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
        # Setup Adapters
        self.data_adapter = get_adapter(settings.provider)
        configured_trading_provider = settings.trading_provider or settings.provider
        if settings.feed_source == "replay_ws":
            # Replay runs must execute in paper mode so fills are simulated deterministically.
            self.trading_provider = "paper"
        else:
            self.trading_provider = configured_trading_provider
        # "paper" is an execution mode, not a broker adapter.
        # In paper mode we still use the configured market-data adapter (for quotes/status).
        if self.trading_provider == "paper":
            self.trading_adapter = self.data_adapter
        else:
            self.trading_adapter = get_adapter(self.trading_provider)
        
        # Setup Executor
        if self.trading_provider == "paper":
            self.executor = PaperExecutor(initial_capital=settings.initial_capital)
        else:
            self.executor = LiveExecutor(adapter=self.trading_adapter)

        self._wire_event_handlers()
        self.journal = JournalManager(
            settings.log_file.replace(".log", "_journal.jsonl"),
            strategy_name=settings.strategy_name,
            timeframe=settings.timeframe,
            capital_context_provider=self._journal_capital_context,
        )

    def _journal_capital_context(self) -> dict[str, Any]:
        total_pnl = self.portfolio.get_total_pnl(self._latest_price_by_symbol)
        capital_available = float(self.settings.initial_capital) + float(total_pnl)
        return {
            "initial_capital": float(self.settings.initial_capital),
            "capital_before_event": capital_available,
            "capital_after_event": capital_available,
            "capital_available": capital_available,
        }

    def _build_feed(self, settings: RuntimeSettings):
        if settings.feed_source == "replay_ws":
            return ReplayWebSocketBarFeed(settings)
        return BrokerPollingBarFeed(settings)

    def _build_strategy(self) -> Strategy:
        strategy_params = load_strategy_params(self.settings.strategy_name)
        strategy_params.update(
            {
                "lot_quantity": self.settings.lot_quantity,
                "lot_size": self.settings.lot_size,
                "capital_model": self.settings.capital_model,
                "initial_capital": self.settings.initial_capital,
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
        # Replay mode needs option chain/quote resolution from historical DB,
        # so strategies can run without live broker dependencies.
        if self.settings.feed_source == "replay_ws":
            setattr(ctx, "market_data_resolver", ReplayOptionDataResolver(self.settings))
        return load_strategy(ctx, self.settings.strategy_name, self.settings.strategy_class_path)

    def _record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._recent_events.append(
            {
                "time": now_ist().isoformat(),
                "type": event_type,
                "payload": payload,
            }
        )

    @staticmethod
    def _normalize_symbol_for_zerodha(symbol: str) -> str:
        alias_map = {
            "NSE:NIFTY50-INDEX": "NSE:NIFTY 50",
            "NSE:NIFTY50": "NSE:NIFTY 50",
            "NSE:BANKNIFTY-INDEX": "NSE:NIFTY BANK",
            "NSE:NIFTYBANK-INDEX": "NSE:NIFTY BANK",
            "NSE:FINNIFTY-INDEX": "NSE:NIFTY FIN SERVICE",
            "NSE:MIDCPNIFTY-INDEX": "NSE:NIFTY MID SELECT",
        }
        return alias_map.get(symbol, symbol)

    def _build_zerodha_order_api_preview(self, order: Any) -> dict[str, Any]:
        normalized = self._normalize_symbol_for_zerodha(order.symbol)
        if ":" in normalized:
            exchange, tradingsymbol = normalized.split(":", 1)
        else:
            exchange, tradingsymbol = "NSE", normalized

        order_type = str(getattr(order.order_type, "value", "MARKET")).upper()
        payload: dict[str, Any] = {
            "exchange": exchange,
            "tradingsymbol": tradingsymbol,
            "transaction_type": str(order.side.value).upper(),
            "quantity": int(order.quantity),
            "order_type": order_type,
            "product": "MIS",
            "validity": "DAY",
            "variety": "regular",
            "tag": (str(order.tag)[:20] if order.tag else "ASTRA"),
        }
        if order.price is not None and order_type != "MARKET":
            payload["price"] = float(order.price)

        curl_parts = [
            "curl -X POST \"https://api.kite.trade/orders/regular\"",
            "-H \"X-Kite-Version: 3\"",
            "-H \"Authorization: token <api_key>:<access_token>\"",
            "-H \"Content-Type: application/x-www-form-urlencoded\"",
        ]
        curl_parts.extend([f"--data-urlencode \"{k}={v}\"" for k, v in payload.items()])

        return {
            "provider": "zerodha",
            "mode": "simulated",
            "transport": "http",
            "maps_to_event": "ORDER_PLACED",
            "executed": False,
            "request": {
                "method": "POST",
                "url": "https://api.kite.trade/orders/regular",
                "content_type": "application/x-www-form-urlencoded",
                "payload": payload,
            },
            "curl_preview": " ".join(curl_parts),
            "note": "Dry-run preview only. Runtime did not execute this HTTP request.",
        }

    def _wire_event_handlers(self) -> None:
        bus.subscribe(EventType.BAR, self._on_bar_event)
        bus.subscribe(EventType.SIGNAL, self._on_signal_event)
        bus.subscribe(EventType.ORDER, self._on_order_event)
        bus.subscribe(EventType.ORDER, self.executor.handle_order_event)
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
                "time": isoformat_ist(bar.timestamp),
                "close": bar.close,
                "volume": bar.volume,
            },
        )

    async def _on_signal_event(self, event: Any) -> None:
        # Astra Signal Journaling
        asyncio.create_task(self.journal.log_indicator_signal(
            event.symbol,
            event.indicator,
            event.value,
            event.threshold,
            event.action,
            basket_id=event.basket_id
        ))
        self._record_event(
            "signal",
            {
                "symbol": event.symbol,
                "indicator": event.indicator,
                "value": event.value,
                "action": event.action,
                "basket_id": event.basket_id
            }
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
        
        # Astra Journaling
        basket_id = getattr(order, "basket_id", "none")
        market_event_ts = isoformat_ist(self._latest_snapshot.bar.timestamp) if self._latest_snapshot else None
        if self._latest_snapshot and self._latest_snapshot.symbol == order.symbol:
            if order.price is None:
                order.price = self._latest_snapshot.bar.close
            order.created_at = self._latest_snapshot.bar.timestamp
        asyncio.create_task(self.journal.log_order(
            order.symbol,
            {
                "order_id": order.order_id,
                "side": order.side.value,
                "quantity": order.quantity,
                "price": order.price,
                "tag": order.tag,
                "status": "PLACED"
            },
            basket_id=basket_id,
            event_ts=market_event_ts,
        ))

        # In replay/paper mode, add a simulated Zerodha HTTP call preview for auditability.
        if self.settings.feed_source == "replay_ws" or self.trading_provider == "paper":
            api_preview = self._build_zerodha_order_api_preview(order)
            asyncio.create_task(
                self.journal.log_event(
                    "BROKER_API_CALL_SIMULATED",
                    order.symbol,
                    api_preview,
                    basket_id=basket_id,
                    event_ts=market_event_ts,
                )
            )

        current_position = self.portfolio.get_position(order.symbol)
        current_quantity = current_position.quantity if current_position else 0
        reference_price = order.price or self._latest_price_by_symbol.get(order.symbol, 0.0)
        if reference_price <= 0 and current_position:
            reference_price = current_position.avg_price

        if order.side == Side.BUY and reference_price > 0:
            decision = self.risk_manager.validate_entry(
                quantity_units=order.quantity,
                lot_size=self.settings.lot_size,
                price=reference_price,
                current_quantity_units=current_quantity,
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
                "filled_at": isoformat_ist(fill.filled_at),
            },
        )
        
        # Astra Journaling
        basket_id = getattr(fill, "basket_id", "none")
        self.portfolio.update_position(fill.symbol, fill.quantity, fill.price, fill.side)
        asyncio.create_task(self.journal.log_fill(
            fill.symbol,
            {
                "order_id": fill.order_id,
                "side": fill.side.value,
                "quantity": fill.quantity,
                "price": fill.price,
                "filled_at": isoformat_ist(fill.filled_at)
            },
            basket_id=basket_id
        ))
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
                "time": isoformat_ist(bar.timestamp),
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
        total_pnl = self.portfolio.get_total_pnl(self._latest_price_by_symbol)
        cash = getattr(self.portfolio, "cash", None)
        equity = getattr(self.portfolio, "equity", None)
        if cash is None:
            # PortfolioManager currently tracks initial_capital + pnl rather than cash/equity fields.
            cash = float(getattr(self.portfolio, "initial_capital", 0.0)) + float(total_pnl)
        if equity is None:
            equity = float(getattr(self.portfolio, "initial_capital", 0.0)) + float(total_pnl)

        return {
            "running": self._running,
            "feed_source": self.settings.feed_source,
            "provider": self.settings.provider,
            "trading_provider": self.trading_provider,
            "run_directory": Path(self.settings.log_file).parent.as_posix(),
            "log_path": Path(self.settings.log_file).as_posix(),
            "journal_path": self.journal.path.as_posix(),
            "symbol": self.settings.symbol,
            "timeframe": self.settings.timeframe,
            "strategy": self.strategy.__class__.__name__,
            "started_at": isoformat_ist(self._started_at) if self._started_at else None,
            "last_error": self._latest_error or None,
            "latest_bar": (
                {
                    "time": isoformat_ist(latest.bar.timestamp),
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
                "cash": cash,
                "equity": equity,
                "realized_pnl": getattr(self.portfolio, "realized_pnl", 0.0),
                "total_pnl": total_pnl,
            },
            "pending_orders": len(self.executor.orders),
            "replay": {
                "url": self.settings.replay_ws_url,
                "data_type": self.settings.replay_data_type,
                "speed": self.settings.replay_speed,
                "completed": getattr(self.feed, "completed", False),
                "error": getattr(self.feed, "error", "") or None,
                "aggregation": (
                    self.feed.get_aggregation_status()
                    if hasattr(self.feed, "get_aggregation_status")
                    else None
                ),
            },
        }

    def get_recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return list(self._recent_events)[-limit:]

    async def get_broker_status(self) -> dict[str, Any]:
        """Fetch live account data from the trading adapter (funds, positions, orders).
        Returns a best-effort dict; each key is None if the adapter does not support it
        or the call fails.
        """
        adapter = self.trading_adapter
        result: dict[str, Any] = {
            "provider": self.trading_provider,
            "funds": None,
            "positions": None,
            "orders": None,
            "error": None,
        }
        errors: list[str] = []

        async def _call(key: str, fn, *args):
            try:
                value = await asyncio.to_thread(fn, *args)
                result[key] = value
            except NotImplementedError:
                pass  # adapter doesn't support this method — leave as None
            except Exception as exc:
                errors.append(f"{key}: {exc}")

        await _call("funds", adapter.get_available_funds)
        await _call("positions", adapter.get_portfolio_status)
        await _call("orders", adapter.get_orders)

        if errors:
            result["error"] = "; ".join(errors)
        return result

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

    async def _recover_from_journal(self) -> None:
        """Replay ORDER_FILL entries from journal to restore portfolio state on restart."""
        fills = self.journal.recover_state()
        if not fills:
            return
        logger.info("Journal recovery: replaying %d fill(s) into portfolio", len(fills))
        for fill in fills:
            symbol = fill["symbol"]
            side_raw = fill["side"].upper()
            qty = fill["quantity"]
            price = fill["price"]
            if not symbol or qty <= 0 or price <= 0:
                continue
            try:
                side = Side.BUY if side_raw == "BUY" else Side.SELL
                self.portfolio.update_position(symbol, qty, price, side)
            except Exception as exc:
                logger.warning("Journal recovery: skipped fill %s — %s", fill, exc)
        logger.info("Journal recovery complete. Portfolio positions: %s", list(self.portfolio.positions.keys()))

    async def _emit_run_header(self) -> None:
        """Write a RUNTIME_HEADER event as the first entry of this run's journal."""
        s = self.settings
        strategy_params = load_strategy_params(s.strategy_name)
        run_params = {
            "run_log_path": s.log_file,
            "feed_source": s.feed_source,
            "provider": s.provider,
            "trading_provider": self.trading_provider,
            "symbol": s.symbol,
            "indicator_input_mode": s.indicator_input_mode,
            "lot_quantity": s.lot_quantity,
            "lot_size": s.lot_size,
            "initial_capital": s.initial_capital,
            "max_position_lots": s.max_position_lots,
            "capital_model": s.capital_model,
            "max_notional_per_trade": s.max_notional_per_trade,
            "stop_loss_pct": s.stop_loss_pct,
            "trailing_stop_pct": s.trailing_stop_pct,
            "replay": {
                "data_type": s.replay_data_type,
                "start_time": s.replay_start_time,
                "end_time": s.replay_end_time,
                "speed": s.replay_speed,
            } if s.feed_source == "replay_ws" else None,
            "strategy_params": strategy_params,
        }
        await self.journal.log_run_header(
            symbol=s.symbol,
            strategy=s.strategy_name,
            timeframe=s.timeframe,
            indicators=list(s.indicators),
            run_params=run_params,
        )
        logger.info(
            "Journal run header written — strategy=%s indicators=%s",
            s.strategy_name,
            s.indicators,
        )

    async def run(self) -> None:
        requires_auth = self.settings.feed_source != "replay_ws"
        if requires_auth:
            try:
                if not auth_manager.is_authenticated(self.settings.provider):
                    logger.warning(f"Provider {self.settings.provider} is not authenticated via API. Attempting to proceed with local token.")
            except Exception as e:
                logger.error(f"Failed to check auth status via DB: {e}. Proceeding in offline/file mode.")

        self._running = True
        self._started_at = now_ist()
        self._latest_error = ""
        self.strategy.on_init()
        self.strategy.on_start()

        # Restore portfolio from journal before entering the main loop
        await self._recover_from_journal()

        # Write a self-describing header as the first new entry of this run's journal.
        # Contains all strategy parameters and indicators for backtracking purposes.
        await self._emit_run_header()

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

        # Self-heal supervisor: restart inner loop on transient errors with backoff.
        MAX_RESTARTS = 5
        restart_count = 0
        backoff = 5  # seconds

        while self._running:
            try:
                await self._run_inner_loop()
                # Clean exit (replay completed or stop() called) — do not restart.
                break
            except Exception as exc:
                self._latest_error = str(exc)
                self._record_event("runtime_error", {"error": str(exc), "restart_count": restart_count})
                logger.exception("Runtime loop error (restart %d/%d): %s", restart_count, MAX_RESTARTS, exc)
                await self.notifier.send(
                    NotificationMessage(
                        title="Strategy runtime error",
                        body=f"[{restart_count}/{MAX_RESTARTS}] {exc}",
                        level="warning",
                    )
                )
                if restart_count >= MAX_RESTARTS:
                    logger.error("Max restarts (%d) reached — runtime halted.", MAX_RESTARTS)
                    self._running = False
                    break
                restart_count += 1
                sleep_secs = backoff * restart_count
                logger.info("Restarting runtime loop in %ds …", sleep_secs)
                await asyncio.sleep(sleep_secs)

        self._running = False

    async def _run_inner_loop(self) -> None:
        """Core market-data loop. Exits cleanly on stop() or replay completion."""
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


def create_runtime(settings: RuntimeSettings) -> StrategyRuntime:
    return StrategyRuntime(settings)