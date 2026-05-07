#!/usr/bin/env python3
"""
Standalone backtest for the nifty_trend_options strategy.

Data sources (both from your DB — no live API calls):
  master_broker.ohlcv_1m                  → NIFTY50 index 1m bars (aggregated to 5m)
  master_broker.options_ohlc_1m_fromupstox → option OHLC for entry/exit pricing

Signal logic mirrors strategy.py exactly:
  Bullish: EMA > SMA  AND  MACD_line > 0  → buy CE
  Bearish: EMA < SMA  AND  MACD_line < 0  → buy PE

Exit logic:
  - Price >= target (entry + 2×risk)  → profit exit
  - Price <= stop   (entry − risk)    → stop exit
  - End of period   → forced close at last available price

Usage:
  python scripts/backtest_nifty_trend.py \\
      --from 2026-04-01 --to 2026-04-28 \\
      --ema-period 20 --sma-period 20 \\
      --macd-fast 12 --macd-slow 26 --macd-signal 9 \\
      --target-premium 200 --premium-tolerance 50 \\
      --sl-pct 0.5 --export-trades trades.csv
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Optional

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


# ── Indicator functions (self-contained, no trading_core import needed) ─────────

def _calc_ema(closes: list[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(closes)
    if len(closes) < period:
        return out
    alpha = 2.0 / (period + 1)
    ema_prev = sum(closes[:period]) / period
    out[period - 1] = ema_prev
    for i in range(period, len(closes)):
        ema_prev = closes[i] * alpha + ema_prev * (1 - alpha)
        out[i] = ema_prev
    return out


def _calc_sma(closes: list[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        out[i] = sum(closes[i - period + 1 : i + 1]) / period
    return out


def _calc_macd(
    closes: list[float], fast: int, slow: int, signal: int
) -> tuple[list[Optional[float]], list[Optional[float]]]:
    """Return (macd_line, signal_line)."""
    ema_fast = _calc_ema(closes, fast)
    ema_slow = _calc_ema(closes, slow)
    macd_line: list[Optional[float]] = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    # Compute signal as EMA of macd_line over the non-None segment
    valid_start = next((i for i, v in enumerate(macd_line) if v is not None), None)
    sig_line: list[Optional[float]] = [None] * len(closes)
    if valid_start is not None:
        valid_values = [v for v in macd_line[valid_start:] if v is not None]
        if len(valid_values) >= signal:
            sig_partial = _calc_ema(valid_values, signal)
            for j, val in enumerate(sig_partial):
                sig_line[valid_start + j] = val
    return macd_line, sig_line


# ── Aggregation 1m → 5m ────────────────────────────────────────────────────────

def _strip_tz(t: datetime) -> datetime:
    return t.replace(tzinfo=None) if getattr(t, "tzinfo", None) else t


def _floor_5m(t: datetime) -> datetime:
    t = _strip_tz(t)
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


def _load_options_bars(
    conn, from_date: str, to_date: str, option_type: str
) -> list[dict]:
    sql = """
        SELECT
            time,
            symbol,
            open, high, low, close,
            strike_price,
            expiry_date,
            option_type,
            nifty_spot
        FROM master_broker.options_ohlc_1m_fromupstox
        WHERE option_type = %s
          AND time >= %s::date
          AND time <  (%s::date + INTERVAL '1 day')
          AND close IS NOT NULL
          AND close > 0
        ORDER BY time, strike_price
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (option_type, from_date, to_date))
        return [dict(r) for r in cur.fetchall()]


# ── Options index helpers ──────────────────────────────────────────────────────

def _build_opts_by_bar(rows: list[dict]) -> dict[datetime, list[dict]]:
    """Group option rows by their 5m bucket."""
    idx: dict[datetime, list[dict]] = defaultdict(list)
    for r in rows:
        idx[_floor_5m(r["time"])].append(r)
    return idx


def _build_symbol_close_index(rows: list[dict]) -> dict[tuple, float]:
    """Last 1m bar price per (5m_bucket, symbol) = the 5m close price."""
    idx: dict[tuple, float] = {}
    for r in rows:
        key = (_floor_5m(r["time"]), r["symbol"])
        idx[key] = float(r["close"])  # overwrite → last row in sort order wins
    return idx


# ── Signal helpers ─────────────────────────────────────────────────────────────

def _bullish(ema, sma, macd) -> bool:
    return ema is not None and sma is not None and macd is not None and ema > sma and macd > 0


def _bearish(ema, sma, macd) -> bool:
    return ema is not None and sma is not None and macd is not None and ema < sma and macd < 0


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
    index_symbol: str = "NSE:NIFTY50-INDEX",
    lot_size: int = 75,
    engine: str = "legacy",
    strategy_name: str = "nifty_trend_options",
    timeframe: str = "5m",
    log_file: str = "logs/strategy_runtime/runtime.log",
    run_name: str = "",
    verbose: bool = True,
) -> dict:
    """
    Run the nifty_trend_options backtest.

    Returns:
        {
          "trades": [ {entry_time, exit_time, direction, symbol,
                       entry_price, exit_price, exit_reason, pnl}, ... ],
          "summary": {total_trades, wins, losses, win_rate_pct,
                      total_pnl, avg_win, avg_loss}
        }
    """
    if verbose:
        print(f"\n{'='*62}")
        print(f"  Backtest  {from_date} → {to_date}")
        print(
            f"  EMA={ema_period}  SMA={sma_period}  "
            f"MACD={macd_fast}/{macd_slow}/{macd_signal_period}"
        )
        print(
            f"  target_premium={target_premium}  ±{premium_tolerance}  "
            f"SL={sl_pct*100:.0f}%  lot={lot_size}"
        )
        print(f"{'='*62}")

    # 1. Index bars → 5m
    rows_1m = _load_index_bars(conn, index_symbol, from_date, to_date)
    if not rows_1m:
        if verbose:
            print(f"  No index bars found for {index_symbol} in {from_date}→{to_date}")
        if engine == "adapter":
            return _run_strategy_adapter_mode(
                bars_5m=[],
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
                lot_size=lot_size,
                log_file=log_file,
                run_name=run_name,
                verbose=verbose,
            )
        return {"trades": [], "summary": {}}

    bars_5m = aggregate_to_5m(rows_1m)
    closes = [b["close"] for b in bars_5m]

    if verbose:
        print(f"  Index: {len(rows_1m)} 1m bars → {len(bars_5m)} 5m bars")

    if engine == "adapter":
        return _run_strategy_adapter_mode(
            bars_5m=bars_5m,
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
            lot_size=lot_size,
            log_file=log_file,
            run_name=run_name,
            verbose=verbose,
        )

    # 2. Indicators
    ema_vals = _calc_ema(closes, ema_period)
    sma_vals = _calc_sma(closes, sma_period)
    macd_line_vals, _ = _calc_macd(closes, macd_fast, macd_slow, macd_signal_period)

    # 3. Options data
    opts_ce_raw = _load_options_bars(conn, from_date, to_date, "CE")
    opts_pe_raw = _load_options_bars(conn, from_date, to_date, "PE")
    if verbose:
        print(f"  Options CE rows: {len(opts_ce_raw)}  PE rows: {len(opts_pe_raw)}")

    opts_ce_by_bar = _build_opts_by_bar(opts_ce_raw)
    opts_pe_by_bar = _build_opts_by_bar(opts_pe_raw)
    symbol_close = _build_symbol_close_index(opts_ce_raw + opts_pe_raw)

    # 4. Simulation loop
    trades: list[dict] = []
    pos_symbol: Optional[str] = None
    pos_entry_price: Optional[float] = None
    pos_target: Optional[float] = None
    pos_stop: Optional[float] = None
    pos_direction: Optional[str] = None
    pos_entry_bar_time: Optional[datetime] = None

    for i, bar in enumerate(bars_5m):
        bar_time = _strip_tz(bar["time"])
        ema = ema_vals[i]
        sma = sma_vals[i]
        macd = macd_line_vals[i]

        # ── Exit check ────────────────────────────────────────────────────────
        if pos_symbol is not None:
            current = symbol_close.get((bar_time, pos_symbol))
            if current is not None:
                if current >= pos_target:
                    pnl = (current - pos_entry_price) * lot_size
                    trades.append(
                        dict(
                            entry_time=pos_entry_bar_time,
                            exit_time=bar_time,
                            direction=pos_direction,
                            symbol=pos_symbol,
                            entry_price=pos_entry_price,
                            exit_price=current,
                            exit_reason="TARGET",
                            pnl=pnl,
                        )
                    )
                    if verbose:
                        print(
                            f"  {bar_time}  EXIT TARGET  {pos_direction}  "
                            f"{pos_symbol}  {pos_entry_price:.1f}→{current:.1f}  "
                            f"PnL=₹{pnl:,.0f}"
                        )
                    pos_symbol = pos_entry_price = pos_target = pos_stop = None
                    pos_direction = pos_entry_bar_time = None
                    continue

                if current <= pos_stop:
                    pnl = (current - pos_entry_price) * lot_size
                    trades.append(
                        dict(
                            entry_time=pos_entry_bar_time,
                            exit_time=bar_time,
                            direction=pos_direction,
                            symbol=pos_symbol,
                            entry_price=pos_entry_price,
                            exit_price=current,
                            exit_reason="STOP",
                            pnl=pnl,
                        )
                    )
                    if verbose:
                        print(
                            f"  {bar_time}  EXIT STOP    {pos_direction}  "
                            f"{pos_symbol}  {pos_entry_price:.1f}→{current:.1f}  "
                            f"PnL=₹{pnl:,.0f}"
                        )
                    pos_symbol = pos_entry_price = pos_target = pos_stop = None
                    pos_direction = pos_entry_bar_time = None
                    continue
            continue  # still in position; skip entry check

        # ── Entry check ───────────────────────────────────────────────────────
        bullish = _bullish(ema, sma, macd)
        bearish = _bearish(ema, sma, macd)
        if not bullish and not bearish:
            continue

        direction = "CE" if bullish else "PE"
        opts_at_bar = (opts_ce_by_bar if direction == "CE" else opts_pe_by_bar).get(
            bar_time, []
        )
        if not opts_at_bar:
            if verbose:
                print(f"  {bar_time}  SIGNAL={direction}  no option data at this bar")
            continue

        # Pick option nearest to target_premium within tolerance
        candidates = [
            (abs(float(opt["close"]) - target_premium), opt, float(opt["close"]))
            for opt in opts_at_bar
            if abs(float(opt["close"]) - target_premium) <= premium_tolerance
        ]
        if not candidates:
            if verbose:
                prices = sorted(float(o["close"]) for o in opts_at_bar)
                print(
                    f"  {bar_time}  SIGNAL={direction}  "
                    f"no option within ±{premium_tolerance} of {target_premium} "
                    f"(available: {prices[0]:.0f}–{prices[-1]:.0f})"
                )
            continue

        candidates.sort(key=lambda x: x[0])
        _, best_opt, entry_price = candidates[0]

        risk = entry_price * sl_pct
        pos_symbol = best_opt["symbol"]
        pos_entry_price = entry_price
        pos_stop = entry_price - risk
        pos_target = entry_price + 2 * risk
        pos_direction = direction
        pos_entry_bar_time = bar_time

        if verbose:
            print(
                f"  {bar_time}  ENTRY {direction}  {pos_symbol}  "
                f"premium={entry_price:.1f}  "
                f"stop={pos_stop:.1f}  target={pos_target:.1f}"
            )

    # Force-close any open position at end of period
    if pos_symbol is not None:
        last_price = pos_entry_price
        for bar in reversed(bars_5m):
            lp = symbol_close.get((_strip_tz(bar["time"]), pos_symbol))
            if lp is not None:
                last_price = lp
                break
        pnl = (last_price - pos_entry_price) * lot_size
        trades.append(
            dict(
                entry_time=pos_entry_bar_time,
                exit_time=_strip_tz(bars_5m[-1]["time"]),
                direction=pos_direction,
                symbol=pos_symbol,
                entry_price=pos_entry_price,
                exit_price=last_price,
                exit_reason="EOD",
                pnl=pnl,
            )
        )
        if verbose:
            print(
                f"  EOD CLOSE  {pos_direction}  {pos_symbol}  "
                f"{pos_entry_price:.1f}→{last_price:.1f}  PnL=₹{pnl:,.0f}"
            )

    # 5. Summary stats
    total = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)
    win_rate = (len(wins) / total * 100) if total else 0.0
    avg_win = (sum(t["pnl"] for t in wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(t["pnl"] for t in losses) / len(losses)) if losses else 0.0

    summary = {
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
    }

    if verbose:
        print(f"\n{'─'*62}")
        print(
            f"  Trades: {total}   Wins: {len(wins)}   Losses: {len(losses)}   "
            f"Win rate: {win_rate:.1f}%"
        )
        print(f"  Total PnL : ₹{total_pnl:>10,.2f}  (lot_size={lot_size})")
        print(f"  Avg win   : ₹{avg_win:>10,.2f}   Avg loss: ₹{avg_loss:>10,.2f}")
        print(f"{'─'*62}")

    result = {"trades": trades, "summary": summary}
    return result


def _run_strategy_adapter_mode(
    *,
    bars_5m: list[dict],
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
    lot_size: int,
    log_file: str,
    run_name: str,
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
        from_date=from_date,
        to_date=to_date,
        strategy_name=strategy_name,
        timeframe=timeframe,
        symbol=index_symbol,
        indicators=[f"ema_{ema_period}", f"sma_{sma_period}", "macd"],
        strategy_params={
            "quantity": lot_size,
            "provider": "paper",
            "underlying_symbol": index_symbol,
            "target_premium": target_premium,
            "premium_tolerance": premium_tolerance,
            "stop_loss_premium_pct": sl_pct,
            "strike_scan_count": 10,
            "ema_period": ema_period,
            "sma_period": sma_period,
            "macd_fast": macd_fast,
            "macd_slow": macd_slow,
            "macd_signal": macd_signal_period,
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
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--index-symbol", default="NSE:NIFTY50-INDEX")
    parser.add_argument(
        "--engine",
        choices=["legacy", "adapter"],
        default="legacy",
        help="Execution engine. Default legacy preserves current behavior.",
    )
    parser.add_argument(
        "--strategy-name",
        default="nifty_trend_options",
        help="Strategy name metadata written into adapter artifacts.",
    )
    parser.add_argument(
        "--timeframe",
        default="5m",
        help="Timeframe metadata written into adapter artifacts.",
    )
    parser.add_argument(
        "--log-file",
        default="logs/strategy_runtime/runtime.log",
        help="Main log path used by adapter artifacts.",
    )
    parser.add_argument(
        "--run-name",
        default="",
        help="Optional run name for adapter artifacts.",
    )
    parser.add_argument(
        "--export-trades", metavar="FILE",
        help="Export trades to CSV (e.g. trades.csv)"
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
            lot_size=args.lot_size,
            index_symbol=args.index_symbol,
            engine=args.engine,
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
