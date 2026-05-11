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
import json
import math
import os
import sys
from itertools import product
from pathlib import Path
from typing import Any

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
from strategy_backtest import _load_index_bars, _run_strategy_adapter_mode, aggregate_to_5m  # noqa: E402


DEFAULT_OPTIMIZER_CONFIG = os.path.join(_config_dir, "strategy_optimize_ranges.json")
PARAM_TYPES: dict[str, type] = {
    "ema_period": int,
    "sma_period": int,
    "macd_fast": int,
    "macd_slow": int,
    "macd_signal_period": int,
    "target_premium": float,
    "premium_tolerance": float,
    "sl_pct": float,
}


def _as_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"1", "true", "yes", "y", "on"}:
            return True
        if token in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _as_int(value: Any, *, field: str, minimum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    return parsed


def _coerce_param_value(name: str, value: Any) -> int | float:
    target_type = PARAM_TYPES[name]
    if target_type is int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Parameter '{name}' must be integer, got: {value}") from exc
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Parameter '{name}' must be numeric, got: {value}") from exc


def _load_optimizer_config(config_path: str) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Optimizer config not found: {config_path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    parameters = payload.get("parameters")
    if not isinstance(parameters, dict) or not parameters:
        raise ValueError("optimizer config must include a non-empty 'parameters' object")

    range_dims: dict[str, list[int | float]] = {}
    fixed_params: dict[str, int | float] = {}
    for name, expected_type in PARAM_TYPES.items():
        if name not in parameters:
            raise ValueError(f"optimizer config missing parameter '{name}'")
        spec = parameters.get(name)
        if not isinstance(spec, dict):
            raise ValueError(f"parameter '{name}' must be an object")
        mode = str(spec.get("mode", "")).strip().lower()
        if mode == "fixed":
            if "value" not in spec:
                raise ValueError(f"parameter '{name}' with mode=fixed requires 'value'")
            fixed_value = _coerce_param_value(name, spec["value"])
            fixed_params[name] = fixed_value if expected_type is float else int(fixed_value)
        elif mode == "range":
            values = spec.get("values")
            if not isinstance(values, list) or not values:
                raise ValueError(f"parameter '{name}' with mode=range requires non-empty 'values' list")
            coerced = [_coerce_param_value(name, item) for item in values]
            normalized = [float(v) if expected_type is float else int(v) for v in coerced]
            range_dims[name] = list(dict.fromkeys(normalized))
        else:
            raise ValueError(f"parameter '{name}' mode must be 'range' or 'fixed'")

    early_stop = payload.get("early_stop")
    if not isinstance(early_stop, dict):
        early_stop = {}
    early_stop_enabled = _as_bool(early_stop.get("enabled", True), default=True)
    early_stop_bar_pct = _as_int(early_stop.get("bar_pct", 10), field="early_stop.bar_pct", minimum=1)
    early_stop_min_bars = _as_int(early_stop.get("min_bars", 200), field="early_stop.min_bars", minimum=1)

    return {
        "path": path.resolve().as_posix(),
        "range_dims": range_dims,
        "fixed_params": fixed_params,
        "early_stop_enabled": early_stop_enabled,
        "early_stop_bar_pct": early_stop_bar_pct,
        "early_stop_min_bars": early_stop_min_bars,
    }


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
    parser.add_argument(
        "--optimizer-config",
        default=DEFAULT_OPTIMIZER_CONFIG,
        help="JSON file that defines optimizer ranges/fixed parameters and early-stop settings.",
    )
    args = parser.parse_args()

    optimizer = _load_optimizer_config(args.optimizer_config)
    range_dims: dict[str, list[int | float]] = optimizer["range_dims"]
    fixed_params: dict[str, int | float] = optimizer["fixed_params"]

    keys = list(range_dims.keys())
    combos = list(product(*[range_dims[k] for k in keys])) if keys else [tuple()]
    n_combos = len(combos)

    if args.max_combos > 0:
        combos = combos[: args.max_combos]
        n_combos = len(combos)

    print(f"Optimizer config path : {optimizer['path']}")
    print(f"Parameter grid        : {n_combos} combinations")
    print(f"Date range    : {args.from_date} → {args.to_date}")
    print(f"Ranking by    : {args.sort_by}  (min_trades={args.min_trades})")
    print(
        "Early-stop    : "
        f"enabled={optimizer['early_stop_enabled']} "
        f"bar_pct={optimizer['early_stop_bar_pct']} "
        f"min_bars={optimizer['early_stop_min_bars']}"
    )
    print(f"Fixed params  : {', '.join(sorted(fixed_params.keys())) if fixed_params else 'none'}")
    print(f"Range params  : {', '.join(keys) if keys else 'none'}")
    print("Running …\n")

    if args.max_combos > 0:
        print(f"Combo cap     : {args.max_combos}")

    conn = psycopg2.connect(DATABASE_URL)
    results: list[dict] = []
    combos_skipped_early = 0
    combos_executed_full = 0
    probe_bars_count = 0
    bars_5m: list[dict[str, Any]] = []

    try:
        rows_1m = _load_index_bars(conn, args.index_symbol, args.from_date, args.to_date)
        bars_5m = aggregate_to_5m(rows_1m)
        total_bars = len(bars_5m)
        if total_bars == 0:
            print("No index bars available for date range/symbol. Exiting.")
            return

        probe_bars_count = min(
            total_bars,
            max(
                optimizer["early_stop_min_bars"],
                int(math.ceil(total_bars * optimizer["early_stop_bar_pct"] / 100.0)),
            ),
        )

        for idx, combo in enumerate(combos):
            params = {**fixed_params, **dict(zip(keys, combo))}
            try:
                if optimizer["early_stop_enabled"] and probe_bars_count < total_bars:
                    probe_result = _run_strategy_adapter_mode(
                        bars_5m=bars_5m[:probe_bars_count],
                        from_date=args.from_date,
                        to_date=args.to_date,
                        strategy_name=args.strategy_name,
                        timeframe=args.timeframe,
                        index_symbol=args.index_symbol,
                        ema_period=int(params["ema_period"]),
                        sma_period=int(params["sma_period"]),
                        macd_fast=int(params["macd_fast"]),
                        macd_slow=int(params["macd_slow"]),
                        macd_signal_period=int(params["macd_signal_period"]),
                        target_premium=float(params["target_premium"]),
                        premium_tolerance=float(params["premium_tolerance"]),
                        sl_pct=float(params["sl_pct"]),
                        lot_size=args.lot_size,
                        lot_quantity=args.lot_quantity,
                        initial_capital=args.initial_capital,
                        capital_model=args.capital_model,
                        log_file=args.log_file,
                        run_name=f"{args.run_name_prefix}_{idx:04d}_probe",
                        verbose=False,
                    )
                    if probe_result.get("summary", {}).get("total_trades", 0) == 0:
                        combos_skipped_early += 1
                        print(
                            f"  combo #{idx} skipped early: 0 trades in "
                            f"first {probe_bars_count}/{total_bars} bars"
                        )
                        continue

                combos_executed_full += 1
                result = _run_strategy_adapter_mode(
                    bars_5m=bars_5m,
                    from_date=args.from_date,
                    to_date=args.to_date,
                    strategy_name=args.strategy_name,
                    timeframe=args.timeframe,
                    index_symbol=args.index_symbol,
                    ema_period=int(params["ema_period"]),
                    sma_period=int(params["sma_period"]),
                    macd_fast=int(params["macd_fast"]),
                    macd_slow=int(params["macd_slow"]),
                    macd_signal_period=int(params["macd_signal_period"]),
                    target_premium=float(params["target_premium"]),
                    premium_tolerance=float(params["premium_tolerance"]),
                    sl_pct=float(params["sl_pct"]),
                    lot_size=args.lot_size,
                    lot_quantity=args.lot_quantity,
                    initial_capital=args.initial_capital,
                    capital_model=args.capital_model,
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

    print("\nOptimizer execution summary:")
    print(f"  combos_total         : {n_combos}")
    print(f"  combos_skipped_early : {combos_skipped_early}")
    print(f"  combos_executed_full : {combos_executed_full}")
    if optimizer["early_stop_enabled"]:
        print(f"  early_stop_probe_bars: {probe_bars_count}")

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
