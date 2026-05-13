from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from services.strategy_runtime.journal import JournalManager
from services.strategy_runtime.time_utils import IST, now_ist


@dataclass(slots=True)
class BacktestArtifactPaths:
    run_name: str
    log_path: str
    journal_path: str
    summary_path: str


def _build_run_name(mode: str, strategy_name: str, run_name: str | None = None) -> str:
    if run_name:
        return run_name
    timestamp = now_ist().strftime("%Y%m%d_%H%M%S")
    return f"{mode}_{strategy_name}_{timestamp}"


def _to_ist_iso(dt_value: datetime | str | None) -> str:
    if isinstance(dt_value, datetime):
        dt = dt_value
    else:
        # Fallback to current time when the value is missing or not datetime.
        return now_ist().isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST).isoformat()


async def _write_journal(
    *,
    strategy_name: str,
    timeframe: str,
    symbol: str,
    journal_path: Path,
    run_params: dict[str, Any],
    indicators: list[str],
    trades: list[dict[str, Any]],
    lot_size: int,
) -> None:
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
        run_params=run_params,
    )

    for index, trade in enumerate(trades, start=1):
        entry_order_id = f"bt_entry_{index:04d}"
        exit_order_id = f"bt_exit_{index:04d}"
        entry_ts = _to_ist_iso(trade.get("entry_time"))
        exit_ts = _to_ist_iso(trade.get("exit_time"))

        # Log entry signal decision on the underlying symbol
        underlying_price = trade.get("underlying_price_at_entry")
        if underlying_price is not None:
            await journal.log_entry_passed(
                symbol=symbol,
                entry_data={
                    "price": underlying_price,
                    "decision": trade.get("decision", "UNKNOWN"),
                    "target_price": round(float(trade.get("target_price", 0)), 2),
                    "stop_price": round(float(trade.get("stop_price", 0)), 2),
                    "option_direction": trade.get("direction"),
                    "order_id": entry_order_id,
                },
                event_ts=entry_ts,
            )

        await journal.log_order(
            symbol=trade.get("symbol", symbol),
            order_data={
                "order_id": entry_order_id,
                "side": "BUY",
                "quantity": lot_size,
                "price": trade.get("entry_price"),
                "tag": f"backtest_entry_{trade.get('direction', '')}",
                "status": "PLACED",
            },
            basket_id="none",
            event_ts=entry_ts,
        )
        await journal.log_fill(
            symbol=trade.get("symbol", symbol),
            fill_data={
                "order_id": entry_order_id,
                "side": "BUY",
                "quantity": lot_size,
                "price": trade.get("entry_price"),
                "filled_at": entry_ts,
            },
            basket_id="none",
        )

        await journal.log_order(
            symbol=trade.get("symbol", symbol),
            order_data={
                "order_id": exit_order_id,
                "side": "SELL",
                "quantity": lot_size,
                "price": trade.get("exit_price"),
                "tag": f"backtest_exit_{trade.get('exit_reason', '').lower()}",
                "status": "PLACED",
                "reason": trade.get("exit_reason"),
            },
            basket_id="none",
            event_ts=exit_ts,
        )
        await journal.log_fill(
            symbol=trade.get("symbol", symbol),
            fill_data={
                "order_id": exit_order_id,
                "side": "SELL",
                "quantity": lot_size,
                "price": trade.get("exit_price"),
                "filled_at": exit_ts,
                "reason": trade.get("exit_reason"),
            },
            basket_id="none",
        )


def emit_backtest_artifacts(
    *,
    mode: str,
    strategy_name: str,
    timeframe: str,
    symbol: str,
    from_date: str,
    to_date: str,
    indicators: list[str],
    run_params: dict[str, Any],
    summary: dict[str, Any],
    trades: list[dict[str, Any]],
    lot_size: int,
    log_file: str,
    run_name: str | None = None,
) -> BacktestArtifactPaths:
    resolved_run_name = _build_run_name(mode=mode, strategy_name=strategy_name, run_name=run_name)
    log_path = Path(log_file)
    if not log_path.is_absolute():
        log_path = Path.cwd() / log_path

    log_path.parent.mkdir(parents=True, exist_ok=True)
    run_summary_dir = log_path.parent.parent / "run_summaries"
    run_summary_dir.mkdir(parents=True, exist_ok=True)
    journal_path = log_path.parent / f"{resolved_run_name}_journal.jsonl"
    summary_path = run_summary_dir / f"{mode}_run_{now_ist().strftime('%Y%m%d_%H%M%S')}.log"

    run_params_with_paths = {
        **run_params,
        "run_log_path": log_path.as_posix(),
        "mode": mode,
        "from_date": from_date,
        "to_date": to_date,
    }

    asyncio.run(
        _write_journal(
            strategy_name=strategy_name,
            timeframe=timeframe,
            symbol=symbol,
            journal_path=journal_path,
            run_params=run_params_with_paths,
            indicators=indicators,
            trades=trades,
            lot_size=lot_size,
        )
    )

    started_at = now_ist().isoformat()
    lines = [
        f"mode={mode}",
        f"strategy={strategy_name}",
        f"symbol={symbol}",
        f"timeframe={timeframe}",
        f"from_date={from_date}",
        f"to_date={to_date}",
        f"started_at={started_at}",
        "outcome=completed",
        f"journal_path={journal_path.as_posix()}",
        f"log_path={log_path.as_posix()}",
        f"total_trades={summary.get('total_trades', 0)}",
        f"total_pnl={summary.get('total_pnl', 0)}",
    ]

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    log_lines = [
        f"[{started_at}] mode={mode} strategy={strategy_name} range={from_date}->{to_date}",
        f"[{now_ist().isoformat()}] trades={summary.get('total_trades', 0)} total_pnl={summary.get('total_pnl', 0)}",
        f"[{now_ist().isoformat()}] journal={journal_path.as_posix()}",
        f"[{now_ist().isoformat()}] summary={summary_path.as_posix()}",
    ]
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    return BacktestArtifactPaths(
        run_name=resolved_run_name,
        log_path=log_path.as_posix(),
        journal_path=journal_path.as_posix(),
        summary_path=summary_path.as_posix(),
    )
