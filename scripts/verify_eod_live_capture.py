import argparse
import asyncio
import contextlib
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
TRADING_CORE_DIR = ROOT_DIR / "packages" / "trading_core"
if str(TRADING_CORE_DIR) not in sys.path:
    sys.path.append(str(TRADING_CORE_DIR))

from trading_core.db import DatabaseManager


IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_LOG_DIR = ROOT_DIR / "logs" / "eod_live_capture"


@dataclass
class TableDayStats:
    table_name: str
    daily_rows: int
    daily_symbols: int
    first_time: datetime | None
    last_time: datetime | None


class TeeStream:
    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate end-of-day live capture health for Fyers and Upstox."
    )
    parser.add_argument(
        "--date",
        help="Target IST date in YYYY-MM-DD. Defaults to current IST date.",
    )
    parser.add_argument(
        "--min-fyers-symbols",
        type=int,
        default=100,
        help="Minimum distinct same-day Fyers tick symbols required for pass.",
    )
    parser.add_argument(
        "--min-upstox-symbols",
        type=int,
        default=20,
        help="Minimum distinct same-day Upstox tick symbols required for pass.",
    )
    parser.add_argument(
        "--max-upstox-symbol-drift",
        type=int,
        default=10,
        help="Maximum allowed difference between Upstox tick symbols and Greeks symbols.",
    )
    parser.add_argument(
        "--max-ohlcv-gap-events",
        type=int,
        default=50,
        help="Maximum allowed gap_events from /db/overview for each ohlcv_1m table.",
    )
    parser.add_argument(
        "--log-dir",
        default=str(DEFAULT_LOG_DIR),
        help="Directory where dated verification logs will be written.",
    )
    return parser.parse_args()


def resolve_target_date(raw_date: str | None) -> date:
    if raw_date:
        return datetime.strptime(raw_date, "%Y-%m-%d").date()
    return datetime.now(IST).date()


def format_dt(value: datetime | None) -> str:
    return value.isoformat() if value else "n/a"


def table_key(schema_name: str, table_name: str) -> str:
    return f"{schema_name}.{table_name}"


def _gap_filter_sql_for_table(table_name: str) -> str:
    # Match data_collector gap logic for historical 1m candles.
    if table_name == "ohlcv_1m":
        return """
          AND time::date = prev_time::date
          AND EXTRACT(ISODOW FROM time) BETWEEN 1 AND 5
          AND time::time BETWEEN TIME '09:15' AND TIME '15:30'
          AND prev_time::time BETWEEN TIME '09:15' AND TIME '15:30'
        """
    return ""


def create_log_path(log_dir: str, target_date: date) -> Path:
    log_root = Path(log_dir)
    log_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    return log_root / f"eod_live_capture_{target_date.isoformat()}_{timestamp}.log"


async def fetch_day_stats(conn, schema_name: str, table_name: str, target_date: date) -> TableDayStats:
    query = f"""
        SELECT
            COUNT(*) AS daily_rows,
            COUNT(DISTINCT symbol) AS daily_symbols,
            MIN(time) AS first_time,
            MAX(time) AS last_time
        FROM {schema_name}.{table_name}
        WHERE (time AT TIME ZONE 'Asia/Kolkata')::date = $1
    """
    record = await conn.fetchrow(query, target_date)
    return TableDayStats(
        table_name=table_key(schema_name, table_name),
        daily_rows=record["daily_rows"] or 0,
        daily_symbols=record["daily_symbols"] or 0,
        first_time=record["first_time"],
        last_time=record["last_time"],
    )


async def fetch_gap_events(conn, schema_name: str, table_name: str, gap_minutes: int = 5) -> int:
    gap_filter_sql = _gap_filter_sql_for_table(table_name)
    query = f"""
        WITH ordered AS (
            SELECT
                symbol,
                time,
                LAG(time) OVER (PARTITION BY symbol ORDER BY time) AS prev_time
            FROM {schema_name}.{table_name}
        )
        SELECT COUNT(*)::bigint AS gap_events
        FROM ordered
        WHERE prev_time IS NOT NULL
          {gap_filter_sql}
          AND time - prev_time > $1::interval
    """
    gap_interval = timedelta(minutes=gap_minutes)
    value = await conn.fetchval(query, gap_interval)
    return int(value or 0)


def print_stat_block(stats: TableDayStats) -> None:
    print(
        f"{stats.table_name}: rows={stats.daily_rows}, symbols={stats.daily_symbols}, "
        f"first={format_dt(stats.first_time)}, last={format_dt(stats.last_time)}"
    )


def print_check(label: str, ok: bool, detail: str) -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}: {detail}")
    return ok


async def main_async(args: argparse.Namespace, target_date: date) -> int:

    pool = await DatabaseManager.get_pool()
    try:
        async with pool.acquire() as conn:
            upstox_ticks = await fetch_day_stats(conn, "broker_upstox", "market_ticks", target_date)
            upstox_greeks = await fetch_day_stats(conn, "broker_upstox", "options_greeks_live", target_date)
            fyers_ticks = await fetch_day_stats(conn, "broker_fyers", "market_ticks", target_date)
            fyers_ohlcv_gap_events = await fetch_gap_events(conn, "broker_fyers", "ohlcv_1m")
            upstox_ohlcv_gap_events = await fetch_gap_events(conn, "broker_upstox", "ohlcv_1m")
    finally:
        await DatabaseManager.close_pool()

    print(f"=== EOD LIVE CAPTURE CHECK | target_date={target_date} IST ===")
    print_stat_block(upstox_ticks)
    print_stat_block(upstox_greeks)
    print_stat_block(fyers_ticks)

    results = []
    results.append(
        print_check(
            "Upstox ticks captured",
            upstox_ticks.daily_rows > 0,
            f"daily_rows={upstox_ticks.daily_rows}",
        )
    )
    results.append(
        print_check(
            "Upstox ticks symbol breadth",
            upstox_ticks.daily_symbols >= args.min_upstox_symbols,
            f"daily_symbols={upstox_ticks.daily_symbols}, min_required={args.min_upstox_symbols}",
        )
    )
    results.append(
        print_check(
            "Upstox Greeks captured",
            upstox_greeks.daily_rows > 0,
            f"daily_rows={upstox_greeks.daily_rows}",
        )
    )
    symbol_drift = abs(upstox_ticks.daily_symbols - upstox_greeks.daily_symbols)
    results.append(
        print_check(
            "Upstox tick/Greeks symbol parity",
            symbol_drift <= args.max_upstox_symbol_drift,
            (
                f"tick_symbols={upstox_ticks.daily_symbols}, greek_symbols={upstox_greeks.daily_symbols}, "
                f"drift={symbol_drift}, max_allowed={args.max_upstox_symbol_drift}"
            ),
        )
    )
    results.append(
        print_check(
            "Fyers ticks captured",
            fyers_ticks.daily_rows > 0,
            f"daily_rows={fyers_ticks.daily_rows}",
        )
    )
    results.append(
        print_check(
            "Fyers multi-expiry symbol breadth",
            fyers_ticks.daily_symbols >= args.min_fyers_symbols,
            f"daily_symbols={fyers_ticks.daily_symbols}, min_required={args.min_fyers_symbols}",
        )
    )

    results.append(
        print_check(
            "Fyers ohlcv gap filter healthy",
            fyers_ohlcv_gap_events <= args.max_ohlcv_gap_events,
            f"gap_events={fyers_ohlcv_gap_events}, max_allowed={args.max_ohlcv_gap_events}",
        )
    )
    results.append(
        print_check(
            "Upstox ohlcv gap filter healthy",
            upstox_ohlcv_gap_events <= args.max_ohlcv_gap_events,
            f"gap_events={upstox_ohlcv_gap_events}, max_allowed={args.max_ohlcv_gap_events}",
        )
    )

    failures = len([item for item in results if not item])
    if failures:
        print(f"RESULT: FAIL ({failures} checks failed)")
        return 1

    print("RESULT: PASS")
    return 0


def main() -> int:
    args = parse_args()
    target_date = resolve_target_date(args.date)
    log_path = create_log_path(args.log_dir, target_date)

    with log_path.open("w", encoding="utf-8") as log_file:
        tee = TeeStream(sys.stdout, log_file)
        with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
            print(f"[INFO] Writing verification log to {log_path}")
            return asyncio.run(main_async(args, target_date))


if __name__ == "__main__":
    raise SystemExit(main())