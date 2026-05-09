#!/usr/bin/env python3
"""
Grid-search parameter optimizer for nifty_trend_options strategy.

Runs strategy_backtest.run_backtest() for every combination of parameters
defined in the GRID below and ranks them by total PnL (or win rate).

Edit the GRID dict to add/remove values before running.

Usage:
    python scripts/strategy_optimize.py \\
      --from 2026-04-01 --to 2026-04-28 \\
      --top 10 --sort-by total_pnl

After seeing the top results, copy the winning params into:
  config/strategy_runtime.paper_live.env   (or the .paper_replay.env)
as the NIFTY_* env vars.
"""
from __future__ import annotations

import argparse
import os
import sys
from itertools import product

import psycopg2
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

# strategy_backtest.py is in the same directory as this script
sys.path.insert(0, os.path.dirname(__file__))
from strategy_backtest import run_backtest  # noqa: E402


# ── Parameter grid ─────────────────────────────────────────────────────────────
# Add more values to any key to widen the search.
# Total combinations = product of all list lengths.
# Current default: 4×4×2×2×2×3×2×3 = 1152 combos (runs in a few minutes).
GRID: dict[str, list] = {
    "ema_period":          [10, 14, 20, 26],
    "sma_period":          [10, 14, 20, 26],
    "macd_fast":           [9, 12],
    "macd_slow":           [21, 26],
    "macd_signal_period":  [7, 9],
    "target_premium":      [150.0, 200.0, 250.0],
    "premium_tolerance":   [40.0, 60.0],
    "sl_pct":              [0.35, 0.50, 0.65],
}


def _combo_count() -> int:
    total = 1
    for v in GRID.values():
        total *= len(v)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grid-search optimizer for nifty_trend_options"
    )
    parser.add_argument("--from", dest="from_date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to",   dest="to_date",   required=True, help="YYYY-MM-DD")
    parser.add_argument("--lot-size",     type=int, default=75)
    parser.add_argument("--lot-quantity", type=int, default=1)
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    parser.add_argument(
        "--capital-model",
        choices=["non_compounding", "compounding"],
        default="non_compounding",
    )
    parser.add_argument("--index-symbol", default="NSE:NIFTY50-INDEX")
    parser.add_argument(
        "--strategy-name",
        default="nifty_trend_options",
        help="Strategy name metadata used for optimizer backtest artifacts.",
    )
    parser.add_argument(
        "--timeframe",
        default="5m",
        help="Timeframe metadata used for optimizer backtest artifacts.",
    )
    parser.add_argument(
        "--log-file",
        default="logs/strategy_runtime/runtime.log",
        help="Main log path used for optimizer backtest artifacts.",
    )
    parser.add_argument(
        "--run-name-prefix",
        default="opt",
        help="Run name prefix used for optimizer backtest artifacts.",
    )
    parser.add_argument(
        "--top", type=int, default=10, help="How many top results to display"
    )
    parser.add_argument(
        "--sort-by",
        choices=["total_pnl", "win_rate_pct", "total_trades"],
        default="total_pnl",
        help="Metric used to rank parameter sets",
    )
    parser.add_argument(
        "--min-trades", type=int, default=3,
        help="Exclude param sets with fewer than this many trades (avoids overfitting to lucky 1-trade runs)"
    )
    parser.add_argument(
        "--max-combos",
        type=int,
        default=0,
        help="Optional cap for number of grid combinations to execute (0 = all).",
    )
    args = parser.parse_args()

    n_combos = _combo_count()
    print(f"Parameter grid: {n_combos} combinations")
    print(f"Date range    : {args.from_date} → {args.to_date}")
    print(f"Ranking by    : {args.sort_by}  (min_trades={args.min_trades})")
    print("Running …\n")

    keys = list(GRID.keys())
    combos = list(product(*[GRID[k] for k in keys]))
    if args.max_combos > 0:
        combos = combos[: args.max_combos]
        n_combos = len(combos)
        print(f"Combo cap     : {args.max_combos}")

    conn = psycopg2.connect(DATABASE_URL)
    results: list[dict] = []

    try:
        for idx, combo in enumerate(combos):
            params = dict(zip(keys, combo))
            try:
                result = run_backtest(
                    conn,
                    from_date=args.from_date,
                    to_date=args.to_date,
                    ema_period=params["ema_period"],
                    sma_period=params["sma_period"],
                    macd_fast=params["macd_fast"],
                    macd_slow=params["macd_slow"],
                    macd_signal_period=params["macd_signal_period"],
                    target_premium=params["target_premium"],
                    premium_tolerance=params["premium_tolerance"],
                    sl_pct=params["sl_pct"],
                    lot_size=args.lot_size,
                    lot_quantity=args.lot_quantity,
                    initial_capital=args.initial_capital,
                    capital_model=args.capital_model,
                    index_symbol=args.index_symbol,
                    engine="adapter",
                    strategy_name=args.strategy_name,
                    timeframe=args.timeframe,
                    log_file=args.log_file,
                    run_name=f"{args.run_name_prefix}_{idx:04d}",
                    verbose=False,
                )
                summary = result["summary"]
                if summary.get("total_trades", 0) >= args.min_trades:
                    row = {**summary, **params}
                    results.append(row)
            except (RuntimeError, OSError, ValueError, TypeError, psycopg2.Error) as exc:
                print(f"  combo #{idx} failed: {exc}")

            if (idx + 1) % 100 == 0 or (idx + 1) == n_combos:
                print(f"  {idx+1}/{n_combos} done …")
    finally:
        conn.close()

    if not results:
        print("\nNo results met the min_trades threshold. Try --min-trades 1")
        return

    results.sort(key=lambda r: r.get(args.sort_by, 0), reverse=True)
    top = results[: args.top]

    sep = "─" * 90
    print(f"\n{'='*90}")
    print(f"  TOP {args.top} RESULTS  (sorted by {args.sort_by})")
    print(f"{'='*90}")
    header = (
        f"{'#':>3}  {'PnL (₹)':>10}  {'Trades':>6}  {'Win%':>6}  "
        f"{'EMA':>4}  {'SMA':>4}  {'MF':>3}  {'MS':>3}  {'MSig':>4}  "
        f"{'TgtP':>6}  {'Tol':>5}  {'SL%':>4}"
    )
    print(header)
    print(sep)
    for rank, r in enumerate(top, 1):
        print(
            f"{rank:>3}  "
            f"₹{r.get('total_pnl', 0):>9,.0f}  "
            f"{r.get('total_trades', 0):>6}  "
            f"{r.get('win_rate_pct', 0):>5.1f}%  "
            f"{r.get('ema_period', ''):>4}  "
            f"{r.get('sma_period', ''):>4}  "
            f"{r.get('macd_fast', ''):>3}  "
            f"{r.get('macd_slow', ''):>3}  "
            f"{r.get('macd_signal_period', ''):>4}  "
            f"{r.get('target_premium', 0):>6.0f}  "
            f"{r.get('premium_tolerance', 0):>5.0f}  "
            f"{r.get('sl_pct', 0)*100:>3.0f}%"
        )

    best = top[0]
    print(f"\n{sep}")
    print("  Best parameters → copy into your strategy env file:")
    print(f"{sep}")
    print(f"  EMA_PERIOD={best.get('ema_period')}")
    print(f"  SMA_PERIOD={best.get('sma_period')}")
    print(
        f"  MACD={best.get('macd_fast')}/{best.get('macd_slow')}/{best.get('macd_signal_period')}"
    )
    print(f"  NIFTY_TARGET_PREMIUM={best.get('target_premium')}")
    print(f"  NIFTY_PREMIUM_TOLERANCE={best.get('premium_tolerance')}")
    print(f"  NIFTY_STOP_LOSS_PREMIUM_PCT={best.get('sl_pct')}")
    print(
        f"\n  Expected PnL   : ₹{best.get('total_pnl', 0):,.0f}  "
        f"over {best.get('total_trades')} trades  "
        f"({best.get('win_rate_pct')}% win rate)"
    )


if __name__ == "__main__":
    main()
