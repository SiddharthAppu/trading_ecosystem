#!/usr/bin/env python3
"""
Standalone backtest entrypoint for strategy_runtime offline adapter.

Execution path:
  scripts/strategy_backtest.py
    -> services.strategy_runtime.offline_adapter.runner.run_strategy_adapter_backtest

Indicators are computed by trading_core analytics (TA-Lib when available,
in-house fallback otherwise).
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse

# ── DB ─────────────────────────────────────────────────────────────────────────
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed.  pip install psycopg2-binary")
    sys.exit(1)

from dotenv import load_dotenv

_config_dir = os.getenv(
    "TRADING_CONFIG_DIR",
    os.path.join(os.path.dirname(__file__), "..", "config"),
)
_env_file = os.path.join(_config_dir, ".env")
if os.path.exists(_env_file):
    load_dotenv(_env_file)

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set. Check config/.env")
    sys.exit(1)


def _database_descriptor(db_url: str) -> str:
    try:
        parsed = urlparse(db_url)
    except (TypeError, ValueError):
        return "unknown"
    host = parsed.hostname or "unknown-host"
    db_name = (parsed.path or "/").lstrip("/") or "unknown-db"
    return f"{host}/{db_name}"


def _floor_5m(t: datetime) -> datetime:
    # Preserve the original timezone so replay lookups stay anchored to the
    # exact instant represented by the source 1m bar.
    return t.replace(minute=(t.minute // 5) * 5, second=0, microsecond=0)


def aggregate_to_5m(rows_1m: list[dict]) -> list[dict]:
    groups: dict[datetime, list[dict]] = defaultdict(list)
    for row in rows_1m:
        groups[_floor_5m(row["time"])].append(row)
    bars: list[dict] = []
    for bucket in sorted(groups):
        chunk = groups[bucket]
        bars.append(
            {
                "time": bucket,
                "open": float(chunk[0]["open"]),
                "high": max(float(r["high"]) for r in chunk),
                "low": min(float(r["low"]) for r in chunk),
                "close": float(chunk[-1]["close"]),
                "volume": sum(int(r.get("volume") or 0) for r in chunk),
            }
        )
    return bars


# ── DB queries ─────────────────────────────────────────────────────────────────

def _load_index_bars(conn, symbol: str, from_date: str, to_date: str) -> list[dict]:
    sql = """
        SELECT
            time,
            COALESCE(open_upstox,  open_fyers)  AS open,
            COALESCE(high_upstox,  high_fyers)  AS high,
            COALESCE(low_upstox,   low_fyers)   AS low,
            master_close                         AS close,
            COALESCE(vol_upstox,   vol_fyers, 0) AS volume
        FROM master_broker.ohlcv_1m
        WHERE symbol = %s
          AND time >= %s::date
          AND time <  (%s::date + INTERVAL '1 day')
          AND master_close IS NOT NULL
        ORDER BY time
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (symbol, from_date, to_date))
        return [dict(r) for r in cur.fetchall()]


# ── Core backtest ──────────────────────────────────────────────────────────────

def run_backtest(
    conn,
    from_date: str,
    to_date: str,
    *,
    ema_period: int = 20,
    sma_period: int = 20,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal_period: int = 9,
    target_premium: float = 200.0,
    premium_tolerance: float = 50.0,
    sl_pct: float = 0.5,
    force_exit_1500_enabled: str = "false",
    force_exit_time_ist: str = "15:00",
    force_exit_debug_enabled: str = "false",
    force_exit_debug_to_journal: str = "false",
    index_symbol: str = "NSE:NIFTY50-INDEX",
    lot_size: int = 75,
    lot_quantity: int = 1,
    initial_capital: float = 100000.0,
    capital_model: str = "non_compounding",
    strategy_name: str = "nifty_trend_options",
    timeframe: str = "5m",
    log_file: str = "logs/strategy_runtime/runtime.log",
    run_name: str = "",
    verbose: bool = True,
) -> dict:
    """Run backtest via strategy_runtime offline adapter."""
    if verbose:
        _lot_qty_label = "auto (-1) — sized from capital each bar" if lot_quantity == -1 else str(lot_quantity)
        print(f"\n{'='*62}")
        print("  Backtest configuration")
        print(f"  {'─'*58}")
        print(f"  Strategy               : {strategy_name}")
        print(f"  Date range             : {from_date} -> {to_date}")
        print(f"  Timeframe              : {timeframe}")
        print(f"  Symbol                 : {index_symbol}")
        print(f"  {'─'*58}")
        print(f"  Capital model          : {capital_model}")
        print(f"  Initial capital        : Rs {initial_capital:,.2f}")
        print(f"  Lot quantity           : {_lot_qty_label}")
        print(f"  Lot size               : {lot_size}")
        print(f"  {'─'*58}")
        print(f"  EMA period             : {ema_period}")
        print(f"  SMA period             : {sma_period}")
        print(f"  MACD                   : {macd_fast}/{macd_slow}/{macd_signal_period}")
        print(f"  Target premium         : {target_premium}  +/-{premium_tolerance}")
        print(f"  Stop loss pct          : {sl_pct*100:.0f}%  (options premium SL)")
        print(f"  Force exit enabled     : {force_exit_1500_enabled}")
        print(f"  Force exit time (IST)  : {force_exit_time_ist}")
        print(f"  Force-exit debug       : {force_exit_debug_enabled}")
        print(f"  Debug to journal       : {force_exit_debug_to_journal}")
        print(f"{'='*62}")

    rows_1m = _load_index_bars(conn, index_symbol, from_date, to_date)
    bars_5m = aggregate_to_5m(rows_1m) if rows_1m else []

    if verbose:
        if rows_1m:
            print(f"  Index: {len(rows_1m)} 1m bars → {len(bars_5m)} 5m bars")
        else:
            print(f"  No index bars found for {index_symbol} in {from_date}→{to_date}")

    return _run_strategy_adapter_mode(
        bars_5m=bars_5m,
        bars_1m=rows_1m,
        from_date=from_date,
        to_date=to_date,
        strategy_name=strategy_name,
        timeframe=timeframe,
        index_symbol=index_symbol,
        ema_period=ema_period,
        sma_period=sma_period,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal_period=macd_signal_period,
        target_premium=target_premium,
        premium_tolerance=premium_tolerance,
        sl_pct=sl_pct,
        force_exit_1500_enabled=force_exit_1500_enabled,
        force_exit_time_ist=force_exit_time_ist,
        force_exit_debug_enabled=force_exit_debug_enabled,
        force_exit_debug_to_journal=force_exit_debug_to_journal,
        lot_size=lot_size,
        lot_quantity=lot_quantity,
        initial_capital=initial_capital,
        capital_model=capital_model,
        log_file=log_file,
        run_name=run_name,
        adapter_mode="backtest",
        verbose=verbose,
    )


def _run_strategy_adapter_mode(
    *,
    bars_5m: list[dict],
    bars_1m: list[dict],
    from_date: str,
    to_date: str,
    strategy_name: str,
    timeframe: str,
    index_symbol: str,
    ema_period: int,
    sma_period: int,
    macd_fast: int,
    macd_slow: int,
    macd_signal_period: int,
    target_premium: float,
    premium_tolerance: float,
    sl_pct: float,
    force_exit_1500_enabled: str,
    force_exit_time_ist: str,
    force_exit_debug_enabled: str,
    force_exit_debug_to_journal: str,
    lot_size: int,
    lot_quantity: int,
    initial_capital: float,
    capital_model: str,
    log_file: str,
    run_name: str,
    adapter_mode: str,
    verbose: bool,
) -> dict:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    try:
        from services.strategy_runtime.offline_adapter.runner import run_strategy_adapter_backtest
    except (ImportError, OSError, ValueError) as exc:
        raise RuntimeError(f"Adapter runner unavailable: {exc}") from exc

    adapter_result = run_strategy_adapter_backtest(
        bars_5m=bars_5m,
        bars_1m=bars_1m,
        from_date=from_date,
        to_date=to_date,
        strategy_name=strategy_name,
        timeframe=timeframe,
        symbol=index_symbol,
        indicators=[f"ema_{ema_period}", f"sma_{sma_period}", "macd"],
        strategy_params={
            "lot_quantity": lot_quantity,
            "lot_size": lot_size,
            "initial_capital": initial_capital,
            "capital_model": capital_model,
            "provider": "paper",
            "underlying_symbol": index_symbol,
            "target_premium": target_premium,
            "premium_tolerance": premium_tolerance,
            "stop_loss_premium_pct": sl_pct,
            "force_exit_1500_enabled": force_exit_1500_enabled,
            "force_exit_time_ist": force_exit_time_ist,
            "force_exit_debug_enabled": force_exit_debug_enabled,
            "force_exit_debug_to_journal": force_exit_debug_to_journal,
            "strike_scan_count": 10,
            "ema_period": ema_period,
            "sma_period": sma_period,
            "macd_fast": macd_fast,
            "macd_slow": macd_slow,
            "macd_signal": macd_signal_period,
            "source_mode": adapter_mode,
            "source_db": _database_descriptor(DATABASE_URL),
            "index_source_table": "master_broker.ohlcv_1m",
            "options_source_table": os.getenv(
                "STRATEGY_RUNTIME_REPLAY_OPTIONS_TABLE",
                "master_broker.options_ohlc_1m_fromupstox",
            ),
        },
        log_file=log_file,
        run_name=run_name or None,
    )
    if verbose:
        print(f"\n  Adapter artifacts → journal={adapter_result.journal_path}")
        print(f"  Adapter artifacts → summary={adapter_result.summary_path}")
    return {
        "trades": adapter_result.trades,
        "summary": adapter_result.summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest nifty_trend_options with historical DB data"
    )
    parser.add_argument("--from", dest="from_date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--ema-period", type=int, default=20)
    parser.add_argument("--sma-period", type=int, default=20)
    parser.add_argument("--macd-fast", type=int, default=12)
    parser.add_argument("--macd-slow", type=int, default=26)
    parser.add_argument("--macd-signal", type=int, default=9)
    parser.add_argument("--target-premium", type=float, default=200.0)
    parser.add_argument("--premium-tolerance", type=float, default=50.0)
    parser.add_argument(
        "--sl-pct",
        type=float,
        default=0.5,
        help="Stop-loss as fraction of entry premium (0.5 = 50%%)",
    )
    parser.add_argument(
        "--force-exit-1500-enabled",
        default=os.getenv("NIFTY_FORCE_EXIT_1500_ENABLED", "false"),
        help="Enable forced exit at/after configured IST time (true/false).",
    )
    parser.add_argument(
        "--force-exit-time-ist",
        default=os.getenv("NIFTY_FORCE_EXIT_TIME_IST", "15:00"),
        help="Forced exit cutoff in IST (HH:MM).",
    )
    parser.add_argument(
        "--force-exit-debug-enabled",
        default=os.getenv("NIFTY_FORCE_EXIT_DEBUG_ENABLED", "false"),
        help="Enable forced-exit debug instrumentation (true/false).",
    )
    parser.add_argument(
        "--force-exit-debug-to-journal",
        default=os.getenv("NIFTY_FORCE_EXIT_DEBUG_TO_JOURNAL", "false"),
        help="Emit forced-exit debug payloads to JSONL journal (true/false).",
    )
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--lot-quantity", type=int, default=1)
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=100000.0,
        help="Initial capital baseline used by adapter capital model.",
    )
    parser.add_argument(
        "--capital-model",
        choices=["non_compounding", "compounding"],
        default="non_compounding",
        help="Capital model used by adapter runner.",
    )
    parser.add_argument("--index-symbol", default="NSE:NIFTY50-INDEX")
    parser.add_argument(
        "--strategy-name",
        default="nifty_trend_options",
        help="Strategy name metadata written into backtest artifacts.",
    )
    parser.add_argument(
        "--timeframe",
        default="5m",
        help="Timeframe metadata written into backtest artifacts.",
    )
    parser.add_argument(
        "--log-file",
        default="logs/strategy_runtime/runtime.log",
        help="Main log path used by backtest artifacts.",
    )
    parser.add_argument(
        "--run-name",
        default="",
        help="Optional run name for backtest artifacts.",
    )
    parser.add_argument(
        "--export-trades",
        metavar="FILE",
        help="Export trades to CSV (e.g. trades.csv)",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    try:
        result = run_backtest(
            conn,
            from_date=args.from_date,
            to_date=args.to_date,
            ema_period=args.ema_period,
            sma_period=args.sma_period,
            macd_fast=args.macd_fast,
            macd_slow=args.macd_slow,
            macd_signal_period=args.macd_signal,
            target_premium=args.target_premium,
            premium_tolerance=args.premium_tolerance,
            sl_pct=args.sl_pct,
            force_exit_1500_enabled=args.force_exit_1500_enabled,
            force_exit_time_ist=args.force_exit_time_ist,
            force_exit_debug_enabled=args.force_exit_debug_enabled,
            force_exit_debug_to_journal=args.force_exit_debug_to_journal,
            lot_size=args.lot_size,
            lot_quantity=args.lot_quantity,
            initial_capital=args.initial_capital,
            capital_model=args.capital_model,
            index_symbol=args.index_symbol,
            strategy_name=args.strategy_name,
            timeframe=args.timeframe,
            log_file=args.log_file,
            run_name=args.run_name,
        )
        if args.export_trades and result["trades"]:
            import csv

            with open(args.export_trades, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(result["trades"][0].keys()))
                writer.writeheader()
                writer.writerows(result["trades"])
            print(f"\n  Trades exported → {args.export_trades}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
