from __future__ import annotations

import asyncio
from dataclasses import dataclass
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
    if symbol_up.endswith("CE"):
        return "CE"
    if symbol_up.endswith("PE"):
        return "PE"
    return "UNK"


def _append_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _summarize_trades(trades: list[dict[str, Any]], bars_5m: list[dict[str, Any]]) -> dict[str, Any]:
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
        "capital_model": "fixed_quantity_non_compounding",
        "pnl_model": "additive_per_trade",
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

    journal = JournalManager(
        journal_path.as_posix(),
        strategy_name=strategy_name,
        timeframe=timeframe,
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
    portfolio = PortfolioManager(initial_capital=1_000_000)
    params = load_strategy_params(strategy_name)
    params.update(strategy_params)
    params.setdefault("provider", "paper")
    params.setdefault("timeframe", timeframe)

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

        order_meta[order.order_id] = {
            "tag": order.tag,
            "basket_id": getattr(order, "basket_id", "none"),
        }

        await journal.log_order(
            order.symbol,
            {
                "order_id": order.order_id,
                "side": order.side.value,
                "quantity": order.quantity,
                "price": order.price,
                "tag": order.tag,
                "status": "PLACED",
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
            },
            basket_id=basket_id,
        )

        if fill.side == Side.BUY:
            open_entries[fill.symbol] = {
                "entry_time": fill.filled_at,
                "entry_price": fill.price,
                "quantity": fill.quantity,
                "direction": _trade_direction(fill.symbol),
            }
            return

        entry = open_entries.pop(fill.symbol, None)
        if not entry:
            return
        qty = int(entry["quantity"])
        pnl = (fill.price - float(entry["entry_price"])) * qty
        exit_tag = str(meta.get("tag") or "EXIT").upper()
        trades.append(
            {
                "entry_time": entry["entry_time"],
                "exit_time": fill.filled_at,
                "direction": entry["direction"],
                "symbol": fill.symbol,
                "entry_price": float(entry["entry_price"]),
                "exit_price": float(fill.price),
                "exit_reason": exit_tag,
                "pnl": pnl,
            }
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

    summary = _summarize_trades(trades, bars_5m)

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
    ]
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    log_lines = [
        f"[{started_at}] mode=backtest strategy={strategy_name} range={from_date}->{to_date}",
        f"[{now_ist().isoformat()}] trading_days={summary['trading_days']} trades={summary['total_trades']} total_pnl={summary['total_pnl']}",
        f"[{now_ist().isoformat()}] max_profit={summary['max_profit']} max_loss={summary['max_loss']} min_profit={summary['min_profit']} min_loss={summary['min_loss']}",
        f"[{now_ist().isoformat()}] max_consecutive_loss_trades={summary['max_consecutive_loss_trades']} capital_model={summary['capital_model']} pnl_model={summary['pnl_model']}",
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
    print(f"  Total PnL                  : ₹{summary['total_pnl']:,.2f}")
    print(f"  Max profit                 : ₹{summary['max_profit']:,.2f}")
    print(f"  Max loss                   : ₹{summary['max_loss']:,.2f}")
    print(f"  Min profit                 : ₹{summary['min_profit']:,.2f}")
    print(f"  Min loss                   : ₹{summary['min_loss']:,.2f}")
    print(f"  Max consecutive loss trades: {summary['max_consecutive_loss_trades']}")
    print(f"  Capital model              : {summary['capital_model']}")
    print(f"  PnL model                  : {summary['pnl_model']}")

    return AdapterBacktestResult(
        trades=trades,
        summary=summary,
        run_name=resolved_run_name,
        log_path=log_path.as_posix(),
        journal_path=journal_path.as_posix(),
        summary_path=summary_path.as_posix(),
    )
