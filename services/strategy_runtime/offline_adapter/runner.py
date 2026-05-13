from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from services.strategy_runtime.bootstrap import ensure_repo_paths

ensure_repo_paths()

from trading_core.analytics import compute_indicator_rows
from trading_core.db import DatabaseManager
from trading_core.events import EventBus, EventType, FillEvent, OrderEvent, SignalEvent
from trading_core.models import Bar, Fill, Order, Side
from trading_core.strategies import StrategyContext

from services.strategy_runtime.journal import JournalManager
from services.strategy_runtime.offline_adapter.artifacts import _build_run_name
from services.strategy_runtime.portfolio import PortfolioManager
from services.strategy_runtime.replay_option_data import ReplayOptionDataResolver
from services.strategy_runtime.strategies import load_strategy, load_strategy_params
from services.strategy_runtime.time_utils import isoformat_ist, now_ist


@dataclass(slots=True)
class AdapterBacktestResult:
    trades: list[dict[str, Any]]
    summary: dict[str, Any]
    run_name: str
    log_path: str
    journal_path: str
    summary_path: str


def _resolve_artifact_paths(*, mode: str, strategy_name: str, run_name: str | None, log_file: str) -> tuple[str, Path, Path, Path]:
    resolved_run_name = _build_run_name(mode=mode, strategy_name=strategy_name, run_name=run_name)
    log_path = Path(log_file)
    if not log_path.is_absolute():
        log_path = Path.cwd() / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    summary_dir = log_path.parent.parent / "run_summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)

    journal_path = log_path.parent / f"{resolved_run_name}_journal.jsonl"
    summary_path = summary_dir / f"{mode}_run_{now_ist().strftime('%Y%m%d_%H%M%S')}.log"
    return resolved_run_name, log_path, journal_path, summary_path


def _trade_direction(symbol: str) -> str:
    symbol_up = symbol.upper()
    if symbol_up.endswith("CE") or " CE " in symbol_up:
        return "CE"
    if symbol_up.endswith("PE") or " PE " in symbol_up:
        return "PE"
    return "UNK"


def _append_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _year_fraction(start: datetime, end: datetime) -> float:
    return max((end - start).total_seconds() / (365.25 * 24 * 3600), 1e-9)


def _parse_iso_date(date_value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(date_value)
    except (TypeError, ValueError):
        return None


def _compute_xirr(cash_flows: list[tuple[datetime, float]]) -> float | None:
    if len(cash_flows) < 2:
        return None
    amounts = [float(amount) for _, amount in cash_flows]
    if not any(amount < 0 for amount in amounts) or not any(amount > 0 for amount in amounts):
        return None

    t0 = min(ts for ts, _ in cash_flows)

    def _npv(rate: float) -> float:
        total = 0.0
        for ts, amount in cash_flows:
            years = _year_fraction(t0, ts)
            total += amount / ((1.0 + rate) ** years)
        return total

    def _d_npv(rate: float) -> float:
        total = 0.0
        for ts, amount in cash_flows:
            years = _year_fraction(t0, ts)
            total += (-years * amount) / ((1.0 + rate) ** (years + 1.0))
        return total

    # Newton-Raphson first for fast convergence.
    rate = 0.1
    for _ in range(100):
        value = _npv(rate)
        deriv = _d_npv(rate)
        if abs(deriv) < 1e-12:
            break
        next_rate = rate - (value / deriv)
        if next_rate <= -0.999999:
            break
        if abs(next_rate - rate) < 1e-10:
            if math.isfinite(next_rate):
                return next_rate
            break
        rate = next_rate

    # Bisection fallback for robustness.
    low = -0.9999
    high = 10.0
    npv_low = _npv(low)
    npv_high = _npv(high)
    if npv_low == 0:
        return low
    if npv_high == 0:
        return high
    if npv_low * npv_high > 0:
        return None

    for _ in range(200):
        mid = (low + high) / 2.0
        npv_mid = _npv(mid)
        if abs(npv_mid) < 1e-8:
            return mid
        if npv_low * npv_mid < 0:
            high = mid
            npv_high = npv_mid
        else:
            low = mid
            npv_low = npv_mid
    return (low + high) / 2.0


def _compute_cagr(
    *,
    start_ts: datetime,
    end_ts: datetime,
    total_invested_capital: float,
    ending_capital: float,
) -> float | None:
    if total_invested_capital <= 0 or ending_capital <= 0:
        return None
    years = _year_fraction(start_ts, end_ts)
    # Very short ranges (for example, intraday debug runs) produce unstable annualization.
    if years < (1.0 / 365.25):
        return None
    return (ending_capital / total_invested_capital) ** (1.0 / years) - 1.0


def _summarize_trades(
    trades: list[dict[str, Any]],
    bars_5m: list[dict[str, Any]],
    *,
    capital_model: str,
    initial_capital: float,
    ending_capital: float,
    refill_events: int,
    refill_amount: float,
    xirr: float | None,
    cagr: float | None,
    insufficient_funds_skips: int = 0,
) -> dict[str, Any]:
    pnls = [float(trade.get("pnl", 0.0)) for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl <= 0]
    positive_pnls = [pnl for pnl in pnls if pnl > 0]
    negative_pnls = [pnl for pnl in pnls if pnl < 0]

    max_profit = max(pnls) if pnls else 0.0
    max_loss = min(negative_pnls) if negative_pnls else 0.0
    min_profit = min(positive_pnls) if positive_pnls else 0.0
    min_loss = max(negative_pnls) if negative_pnls else 0.0

    max_loss_streak = 0
    current_loss_streak = 0
    for pnl in pnls:
        if pnl <= 0:
            current_loss_streak += 1
            max_loss_streak = max(max_loss_streak, current_loss_streak)
        else:
            current_loss_streak = 0

    trading_days = len({bar["time"].date() for bar in bars_5m if bar.get("time")})
    total = len(trades)
    total_pnl = sum(pnls)
    win_rate = (len(wins) / total * 100.0) if total else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0

    return {
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "trading_days": trading_days,
        "max_profit": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "min_profit": round(min_profit, 2),
        "min_loss": round(min_loss, 2),
        "max_consecutive_loss_trades": max_loss_streak,
        "capital_model": capital_model,
        "pnl_model": "additive_per_trade",
        "initial_capital": round(initial_capital, 2),
        "ending_capital": round(ending_capital, 2),
        "total_invested_capital": round(initial_capital + refill_amount, 2),
        "refill_events": int(refill_events),
        "refill_amount": round(refill_amount, 2),
        "insufficient_funds_skips": int(insufficient_funds_skips),
        "xirr_pct": round(xirr * 100.0, 4) if xirr is not None else None,
        "cagr_pct": round(cagr * 100.0, 4) if cagr is not None else None,
    }


def run_strategy_adapter_backtest(
    *,
    bars_5m: list[dict[str, Any]],
    from_date: str,
    to_date: str,
    strategy_name: str,
    timeframe: str,
    symbol: str,
    indicators: list[str],
    strategy_params: dict[str, Any],
    log_file: str,
    run_name: str | None = None,
) -> AdapterBacktestResult:
    # ── Print run configuration before any async work ──────────────────────
    _raw_lot_qty = int(strategy_params.get("lot_quantity", 1))
    _lot_size = max(1, int(strategy_params.get("lot_size", 1)))
    _initial_capital = float(strategy_params.get("initial_capital", 100000.0))
    _capital_model = str(strategy_params.get("capital_model", "non_compounding")).strip().lower()
    _auto_lot = _raw_lot_qty == -1
    _lot_qty_label = "auto (-1) — sized from capital each bar" if _auto_lot else str(_raw_lot_qty)
    _stop_loss_pct = strategy_params.get("stop_loss_pct", "")
    _trailing_stop_pct = strategy_params.get("trailing_stop_pct", "")
    _max_position_lots = strategy_params.get("max_position_lots", "")
    print(flush=True)
    print("  ── Backtest configuration ──────────────────────────────────────", flush=True)
    print(f"    Strategy               : {strategy_name}", flush=True)
    print(f"    Date range             : {from_date} -> {to_date}", flush=True)
    print(f"    Timeframe              : {timeframe}", flush=True)
    print(f"    Symbol                 : {symbol}", flush=True)
    print(f"    Indicators             : {', '.join(indicators) if indicators else 'none'}", flush=True)
    print(f"    Capital model          : {_capital_model}", flush=True)
    print(f"    Initial capital        : Rs {_initial_capital:,.2f}", flush=True)
    print(f"    Lot quantity           : {_lot_qty_label}", flush=True)
    print(f"    Lot size               : {_lot_size}", flush=True)
    if _stop_loss_pct != "":
        print(f"    Stop loss pct          : {_stop_loss_pct} (live/replay only, not enforced in BT)", flush=True)
    if _trailing_stop_pct != "":
        print(f"    Trailing stop pct      : {_trailing_stop_pct} (live/replay only, not enforced in BT)", flush=True)
    if _max_position_lots != "":
        print(f"    Max position lots      : {_max_position_lots} (live/replay only, not enforced in BT)", flush=True)
    print(f"    Total 5m bars          : {len(bars_5m)}", flush=True)
    _extra_keys = {
        k: v for k, v in strategy_params.items()
        if k not in {"lot_quantity", "lot_size", "initial_capital", "capital_model",
                     "stop_loss_pct", "trailing_stop_pct", "max_position_lots",
                     "provider", "timeframe", "underlying_symbol"}
    }
    if _extra_keys:
        print("    Strategy params        :", flush=True)
        for k, v in sorted(_extra_keys.items()):
            print(f"      {k:<26}: {v}", flush=True)
    print("  ────────────────────────────────────────────────────────────────", flush=True)
    print(flush=True)
    # ───────────────────────────────────────────────────────────────────────
    return asyncio.run(
        _run_strategy_adapter_backtest(
            bars_5m=bars_5m,
            from_date=from_date,
            to_date=to_date,
            strategy_name=strategy_name,
            timeframe=timeframe,
            symbol=symbol,
            indicators=indicators,
            strategy_params=strategy_params,
            log_file=log_file,
            run_name=run_name,
        )
    )


async def _run_strategy_adapter_backtest(
    *,
    bars_5m: list[dict[str, Any]],
    from_date: str,
    to_date: str,
    strategy_name: str,
    timeframe: str,
    symbol: str,
    indicators: list[str],
    strategy_params: dict[str, Any],
    log_file: str,
    run_name: str | None,
) -> AdapterBacktestResult:
    resolved_run_name, log_path, journal_path, summary_path = _resolve_artifact_paths(
        mode="backtest",
        strategy_name=strategy_name,
        run_name=run_name,
        log_file=log_file,
    )

    initial_capital = float(strategy_params.get("initial_capital", 100000.0))
    lot_size = max(1, int(strategy_params.get("lot_size", 1)))
    _raw_lot_quantity = int(strategy_params.get("lot_quantity", 1))
    auto_lot_mode = _raw_lot_quantity == -1
    lot_quantity = 1 if auto_lot_mode else max(1, _raw_lot_quantity)
    capital_model = str(strategy_params.get("capital_model", "non_compounding")).strip().lower()

    capital_available = initial_capital
    refill_events = 0
    refill_amount = 0.0
    insufficient_funds_skips = 0
    refill_cash_flows: list[tuple[datetime, float]] = []

    def _journal_capital_context() -> dict[str, Any]:
        return {
            "initial_capital": float(initial_capital),
            "capital_before_event": float(capital_available),
            "capital_after_event": float(capital_available),
            "capital_available": float(capital_available),
        }

    journal = JournalManager(
        journal_path.as_posix(),
        strategy_name=strategy_name,
        timeframe=timeframe,
        capital_context_provider=_journal_capital_context,
    )
    await journal.log_run_header(
        symbol=symbol,
        strategy=strategy_name,
        timeframe=timeframe,
        indicators=indicators,
        run_params={
            **strategy_params,
            "mode": "backtest",
            "from_date": from_date,
            "to_date": to_date,
            "run_log_path": log_path.as_posix(),
        },
    )

    event_bus = EventBus()
    portfolio = PortfolioManager(initial_capital=initial_capital)
    params = load_strategy_params(strategy_name)
    params.update(strategy_params)
    params.setdefault("provider", "paper")
    params.setdefault("timeframe", timeframe)
    params.setdefault("lot_size", lot_size)
    params.setdefault("lot_quantity", lot_quantity)
    params.setdefault("capital_model", capital_model)
    params.setdefault("initial_capital", initial_capital)

    ctx = StrategyContext(event_bus, params, strategy_name=strategy_name)
    ctx.link_portfolio(portfolio)
    resolver = ReplayOptionDataResolver(SimpleNamespace())
    setattr(ctx, "market_data_resolver", resolver)
    strategy = load_strategy(ctx, strategy_name)

    rows = [
        {
            "time": bar["time"],
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"]),
            "volume": int(bar.get("volume") or 0),
        }
        for bar in bars_5m
    ]
    compute_indicator_rows(rows, indicators)

    trades: list[dict[str, Any]] = []
    open_entries: dict[str, dict[str, Any]] = {}
    order_meta: dict[str, dict[str, Any]] = {}
    bars_history: list[Bar] = []
    current_bar: Bar | None = None

    async def _on_signal(event: SignalEvent) -> None:
        if event.indicator == "force_exit_debug" and isinstance(event.value, dict):
            await journal.log_event(
                "FORCE_EXIT_DEBUG",
                event.symbol,
                event.value,
                basket_id=event.basket_id,
            )
            return
        await journal.log_indicator_signal(
            event.symbol,
            event.indicator,
            event.value,
            event.threshold,
            event.action,
            basket_id=event.basket_id,
        )

    async def _on_order(event: OrderEvent) -> None:
        order = event.order
        if current_bar is not None:
            if order.price is None:
                order.price = current_bar.close
            order.created_at = current_bar.timestamp
            event_ts = isoformat_ist(current_bar.timestamp)
        else:
            event_ts = now_ist().isoformat()

        existing_entry = open_entries.get(order.symbol)
        if order.side == Side.BUY:
            trade_id = f"trd_{order.order_id}"
        else:
            trade_id = str(existing_entry.get("trade_id")) if existing_entry and existing_entry.get("trade_id") else f"trd_{order.order_id}"

        order_meta[order.order_id] = {
            "tag": order.tag,
            "basket_id": getattr(order, "basket_id", "none"),
            "underlying_price": current_bar.close if current_bar else None,
            "bar_timestamp": current_bar.timestamp if current_bar else None,
            "trade_id": trade_id,
        }

        if order.side == Side.BUY and current_bar is not None:
            direction = _trade_direction(order.symbol)
            decision = "BULLISH" if direction == "CE" else ("BEARISH" if direction == "PE" else "UNKNOWN")
            await journal.log_entry_passed(
                symbol=symbol,
                entry_data={
                    "price": float(current_bar.close),
                    "decision": decision,
                    "option_symbol": order.symbol,
                    "option_price": float(order.price or 0.0),
                    "order_id": order.order_id,
                    "trade_id": trade_id,
                },
                basket_id=getattr(order, "basket_id", "none"),
                event_ts=event_ts,
            )

        await journal.log_order(
            order.symbol,
            {
                "order_id": order.order_id,
                "side": order.side.value,
                "quantity": order.quantity,
                "price": order.price,
                "tag": order.tag,
                "status": "PLACED",
                "trade_id": trade_id,
            },
            basket_id=getattr(order, "basket_id", "none"),
            event_ts=event_ts,
        )

        fill = Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=float(order.price or 0.0),
            filled_at=order.created_at,
        )
        await event_bus.publish(FillEvent(fill=fill))

    async def _on_fill(event: FillEvent) -> None:
        nonlocal capital_available, refill_events, refill_amount

        fill = event.fill
        meta = order_meta.get(fill.order_id, {})
        basket_id = str(meta.get("basket_id", "none"))

        portfolio.update_position(fill.symbol, fill.quantity, fill.price, fill.side)
        await journal.log_fill(
            fill.symbol,
            {
                "order_id": fill.order_id,
                "side": fill.side.value,
                "quantity": fill.quantity,
                "price": fill.price,
                "filled_at": isoformat_ist(fill.filled_at),
                "trade_id": meta.get("trade_id"),
            },
            basket_id=basket_id,
        )

        if fill.side == Side.BUY:
            direction = _trade_direction(fill.symbol)
            underlying_price = order_meta.get(fill.order_id, {}).get("underlying_price")
            bar_timestamp = order_meta.get(fill.order_id, {}).get("bar_timestamp")
            open_entries[fill.symbol] = {
                "entry_time": fill.filled_at,
                "entry_price": fill.price,
                "quantity": fill.quantity,
                "direction": direction,
                "underlying_price_at_entry": underlying_price,
                "bar_timestamp": bar_timestamp,
                "order_id": fill.order_id,
                "trade_id": meta.get("trade_id"),
            }
            return

        entry = open_entries.pop(fill.symbol, None)
        if not entry:
            return
        qty = int(entry["quantity"])
        capital_before = float(capital_available)
        pnl = (fill.price - float(entry["entry_price"])) * qty
        capital_available = float(capital_available + pnl)
        exit_tag = str(meta.get("tag") or "EXIT").upper()
        
        # Calculate entry decision and price targets for charting
        direction = entry["direction"]
        entry_price = float(entry["entry_price"])
        stop_loss_pct = float(strategy_params.get("stop_loss_premium_pct", 0.35))
        risk = entry_price * stop_loss_pct
        target_price = entry_price + (2 * risk)
        stop_price = entry_price - risk
        decision = "BULLISH" if direction == "CE" else "BEARISH"
        
        trades.append(
            {
                "entry_time": entry["entry_time"],
                "exit_time": fill.filled_at,
                "direction": direction,
                "symbol": fill.symbol,
                "entry_price": entry_price,
                "exit_price": float(fill.price),
                "exit_reason": exit_tag,
                "pnl": pnl,
                "capital_before": capital_before,
                "capital_after": float(capital_available),
                # Entry decision data for ENTRY_PASSED logging
                "underlying_price_at_entry": entry.get("underlying_price_at_entry"),
                "bar_timestamp_at_entry": entry.get("bar_timestamp"),
                "decision": decision,
                "target_price": target_price,
                "stop_price": stop_price,
                "trade_id": entry.get("trade_id"),
            }
        )

        refill_topup = 0.0
        if capital_available <= 0:
            refill_topup = float(initial_capital - capital_available)
        elif capital_model == "non_compounding" and capital_available < initial_capital:
            refill_topup = float(initial_capital - capital_available)

        if refill_topup > 0:
            refill_events += 1
            refill_amount += refill_topup
            refill_cash_flows.append((fill.filled_at, refill_topup))
            refill_before = float(capital_available)
            capital_available = float(capital_available + refill_topup)
            await journal.log_event(
                "INITIAL_CAPITAL_REFILL",
                fill.symbol,
                {
                    "reason": "capital_refill",
                    "refill_amount": round(refill_topup, 2),
                    "triggered_by_order_id": fill.order_id,
                    "trade_id": meta.get("trade_id"),
                },
                basket_id=basket_id,
                event_ts=isoformat_ist(fill.filled_at),
                capital_context={
                    "initial_capital": float(initial_capital),
                    "capital_before_event": refill_before,
                    "capital_after_event": float(capital_available),
                    "capital_available": float(capital_available),
                },
            )

    event_bus.subscribe(EventType.SIGNAL, _on_signal)
    event_bus.subscribe(EventType.ORDER, _on_order)
    event_bus.subscribe(EventType.FILL, _on_fill)

    try:
        for row in rows:
            bar = Bar(
                symbol=symbol,
                timestamp=row["time"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row.get("volume") or 0),
                timeframe=timeframe,
            )
            current_bar = bar
            bars_history.append(bar)

            indicator_payload: dict[str, Any] = {
                "ema_20": row.get("ema_20"),
                "sma_20": row.get("sma_20"),
                "rsi_14": row.get("rsi_14"),
                "macd_line": row.get("macd_line"),
                "macd_signal": row.get("macd_signal"),
                "macd_histogram": row.get("macd_histogram"),
                # Some strategies read a dict-valued macd key.
                "macd": {
                    "macd": row.get("macd_line"),
                    "signal": row.get("macd_signal"),
                    "hist": row.get("macd_histogram"),
                },
            }
            snapshot = SimpleNamespace(
                symbol=symbol,
                timeframe=timeframe,
                bar=bar,
                bars=list(bars_history),
                indicators=indicator_payload,
            )

            if hasattr(strategy, "evaluate_snapshot"):
                one_lot_cost = float(bar.close) * lot_size if lot_size > 0 else 0.0
                # Auto-lot sizing (-1 sentinel) applies to both capital models.
                if auto_lot_mode:
                    if one_lot_cost > 0:
                        dynamic_lots = math.floor(capital_available / one_lot_cost)
                    else:
                        dynamic_lots = 1
                    # In auto-lot mode: skip bar if can't afford one lot and no open position.
                    if dynamic_lots < 1 and not open_entries:
                        insufficient_funds_skips += 1
                        await journal.log_event(
                            "INSUFFICIENT_FUNDS_SKIP",
                            symbol,
                            {
                                "required_for_one_lot": round(one_lot_cost, 2),
                                "capital_available": round(capital_available, 2),
                                "lot_size": lot_size,
                                "capital_model": capital_model,
                                "reason": "insufficient_capital_for_one_lot",
                            },
                            basket_id="none",
                            event_ts=isoformat_ist(bar.timestamp),
                        )
                        continue
                    ctx.params["lot_quantity"] = max(1, dynamic_lots)
                elif capital_model == "compounding":
                    if one_lot_cost > 0:
                        dynamic_lots = max(1, math.floor(capital_available / one_lot_cost))
                    else:
                        dynamic_lots = lot_quantity
                    ctx.params["lot_quantity"] = dynamic_lots
                await strategy.evaluate_snapshot(snapshot)
            else:
                await strategy.on_bar(bar)

        if current_bar is not None and open_entries:
            for open_symbol, entry in list(open_entries.items()):
                try:
                    quotes = await resolver.get_quotes([open_symbol], current_bar.timestamp)
                    exit_price = float(quotes[0]["last_price"]) if quotes else float(entry["entry_price"])
                except (OSError, RuntimeError, ValueError, TypeError):
                    exit_price = float(entry["entry_price"])

                eod_order = Order(
                    symbol=open_symbol,
                    side=Side.SELL,
                    quantity=int(entry["quantity"]),
                    price=exit_price,
                    tag="EOD",
                )
                eod_order.created_at = current_bar.timestamp
                await event_bus.publish(OrderEvent(order=eod_order, action="SUBMITTED"))
    finally:
        await DatabaseManager.close_pool()

    from_date_dt = _parse_iso_date(from_date)
    to_date_dt = _parse_iso_date(to_date)
    if from_date_dt is not None and to_date_dt is not None:
        run_start_ts = from_date_dt
        run_end_ts = to_date_dt + timedelta(days=1)
    elif bars_5m:
        run_start_ts = bars_5m[0]["time"]
        run_end_ts = bars_5m[-1]["time"]
    else:
        run_start_ts = now_ist()
        run_end_ts = run_start_ts

    cash_flows: list[tuple[datetime, float]] = [(run_start_ts, -initial_capital)]
    cash_flows.extend((ts, -amount) for ts, amount in refill_cash_flows)
    cash_flows.append((run_end_ts, capital_available))

    xirr = _compute_xirr(cash_flows)
    cagr = _compute_cagr(
        start_ts=run_start_ts,
        end_ts=run_end_ts,
        total_invested_capital=initial_capital + refill_amount,
        ending_capital=capital_available,
    )

    summary = _summarize_trades(
        trades,
        bars_5m,
        capital_model=capital_model,
        initial_capital=initial_capital,
        ending_capital=capital_available,
        refill_events=refill_events,
        refill_amount=refill_amount,
        xirr=xirr,
        cagr=cagr,
        insufficient_funds_skips=insufficient_funds_skips,
    )

    started_at = now_ist().isoformat()
    summary_lines = [
        "mode=backtest",
        f"run_name={resolved_run_name}",
        f"strategy={strategy_name}",
        f"symbol={symbol}",
        f"timeframe={timeframe}",
        f"from_date={from_date}",
        f"to_date={to_date}",
        f"started_at={started_at}",
        "outcome=completed",
        f"journal_path={journal_path.as_posix()}",
        f"log_path={log_path.as_posix()}",
        f"trading_days={summary['trading_days']}",
        f"total_trades={summary['total_trades']}",
        f"total_pnl={summary['total_pnl']}",
        f"max_profit={summary['max_profit']}",
        f"max_loss={summary['max_loss']}",
        f"min_profit={summary['min_profit']}",
        f"min_loss={summary['min_loss']}",
        f"max_consecutive_loss_trades={summary['max_consecutive_loss_trades']}",
        f"capital_model={summary['capital_model']}",
        f"pnl_model={summary['pnl_model']}",
        f"initial_capital={summary['initial_capital']}",
        f"ending_capital={summary['ending_capital']}",
        f"total_invested_capital={summary['total_invested_capital']}",
        f"refill_events={summary['refill_events']}",
        f"refill_amount={summary['refill_amount']}",
        f"insufficient_funds_skips={summary['insufficient_funds_skips']}",
        f"xirr_pct={summary['xirr_pct']}",
        f"cagr_pct={summary['cagr_pct']}",
    ]
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    log_lines = [
        f"[{started_at}] mode=backtest strategy={strategy_name} range={from_date}->{to_date}",
        f"[{now_ist().isoformat()}] trading_days={summary['trading_days']} trades={summary['total_trades']} total_pnl={summary['total_pnl']}",
        f"[{now_ist().isoformat()}] max_profit={summary['max_profit']} max_loss={summary['max_loss']} min_profit={summary['min_profit']} min_loss={summary['min_loss']}",
        f"[{now_ist().isoformat()}] max_consecutive_loss_trades={summary['max_consecutive_loss_trades']} capital_model={summary['capital_model']} pnl_model={summary['pnl_model']}",
        f"[{now_ist().isoformat()}] initial_capital={summary['initial_capital']} ending_capital={summary['ending_capital']} total_invested_capital={summary['total_invested_capital']} refill_events={summary['refill_events']} refill_amount={summary['refill_amount']} insufficient_funds_skips={summary['insufficient_funds_skips']}",
        f"[{now_ist().isoformat()}] xirr_pct={summary['xirr_pct']} cagr_pct={summary['cagr_pct']}",
        f"[{now_ist().isoformat()}] journal={journal_path.as_posix()}",
        f"[{now_ist().isoformat()}] summary={summary_path.as_posix()}",
    ]
    _append_lines(log_path, log_lines)

    print()
    print("  Backtest summary")
    print(f"  Trading days               : {summary['trading_days']}")
    print(f"  Total trades               : {summary['total_trades']}")
    print(f"  Wins / Losses              : {summary['wins']} / {summary['losses']}")
    print(f"  Win rate                   : {summary['win_rate_pct']}%")
    print(f"  Total PnL                  : Rs {summary['total_pnl']:,.2f}")
    print(f"  Max profit                 : Rs {summary['max_profit']:,.2f}")
    print(f"  Max loss                   : Rs {summary['max_loss']:,.2f}")
    print(f"  Min profit                 : Rs {summary['min_profit']:,.2f}")
    print(f"  Min loss                   : Rs {summary['min_loss']:,.2f}")
    print(f"  Max consecutive loss trades: {summary['max_consecutive_loss_trades']}")
    print(f"  Capital model              : {summary['capital_model']}")
    print(f"  PnL model                  : {summary['pnl_model']}")
    print(f"  Initial capital            : Rs {summary['initial_capital']:,.2f}")
    print(f"  Ending capital             : Rs {summary['ending_capital']:,.2f}")
    print(f"  Total invested capital     : Rs {summary['total_invested_capital']:,.2f}")
    print(f"  Refill events              : {summary['refill_events']}")
    print(f"  Refill amount              : Rs {summary['refill_amount']:,.2f}")
    print(f"  Insufficient funds skips   : {summary['insufficient_funds_skips']}")
    print(f"  XIRR                       : {summary['xirr_pct'] if summary['xirr_pct'] is not None else 'NA'}%")
    print(f"  CAGR                       : {summary['cagr_pct'] if summary['cagr_pct'] is not None else 'NA'}%")

    return AdapterBacktestResult(
        trades=trades,
        summary=summary,
        run_name=resolved_run_name,
        log_path=log_path.as_posix(),
        journal_path=journal_path.as_posix(),
        summary_path=summary_path.as_posix(),
    )
