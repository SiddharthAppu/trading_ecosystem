import argparse
import asyncio
import subprocess
import sys
from datetime import date, datetime, time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
TRADING_CORE_DIR = ROOT_DIR / "packages" / "trading_core"

if str(TRADING_CORE_DIR) not in sys.path:
    sys.path.append(str(TRADING_CORE_DIR))

from trading_core.db import DatabaseManager


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_iso_time(value: str) -> time:
    return time.fromisoformat(value)


def chunked_dates(values: list[date], chunk_size: int) -> list[list[date]]:
    return [values[index : index + chunk_size] for index in range(0, len(values), chunk_size)]


async def load_trading_days(underlying_symbol: str, market_open_time: str) -> list[date]:
    pool = await DatabaseManager.get_pool()
    query = """
        SELECT DISTINCT time::date AS trade_day
        FROM broker_upstox.ohlcv_1m
        WHERE symbol = $1
          AND time::time = $2::time
        ORDER BY trade_day
    """
    async with pool.acquire() as connection:
        rows = await connection.fetch(query, underlying_symbol, market_open_time)
    return [row["trade_day"] for row in rows]


def build_sync_command(
    sync_script: Path,
    chunk_start: date,
    chunk_end: date,
    underlying_symbol: str,
    max_expiries_per_day: int,
    dry_run: bool,
    verbose: bool,
) -> list[str]:
    command = [
        sys.executable,
        str(sync_script),
        "--start-date",
        chunk_start.isoformat(),
        "--end-date",
        chunk_end.isoformat(),
        "--underlying-symbol",
        underlying_symbol,
        "--max-expiries-per-day",
        str(max_expiries_per_day),
    ]
    if dry_run:
        command.append("--dry-run")
    if verbose:
        command.append("--verbose")
    return command


async def async_main() -> None:
    parser = argparse.ArgumentParser(
        description="Run upstox_options_sync.py across all available ohlcv_1m trading days in chunks.",
    )
    parser.add_argument(
        "--underlying-symbol",
        default="NSE:NIFTY50-INDEX",
        help="Underlying symbol in broker_upstox.ohlcv_1m used to discover trading days.",
    )
    parser.add_argument(
        "--market-open-time",
        default="09:15:00",
        help="Market open candle time used to detect available trading days.",
    )
    parser.add_argument(
        "--max-expiries-per-day",
        type=int,
        default=4,
        help="Cap active expiries per day passed to upstox_options_sync.py.",
    )
    parser.add_argument(
        "--chunk-trading-days",
        type=int,
        default=30,
        help="How many trading days to include in each sync invocation.",
    )
    parser.add_argument(
        "--start-date",
        default="",
        help="Optional lower bound in YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="Optional upper bound in YYYY-MM-DD.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass through dry-run to upstox_options_sync.py.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Pass through verbose logs to upstox_options_sync.py.",
    )
    args = parser.parse_args()

    if args.chunk_trading_days <= 0:
        raise ValueError("chunk-trading-days must be greater than 0")
    if args.max_expiries_per_day < 0:
        raise ValueError("max-expiries-per-day cannot be negative")

    user_start = parse_iso_date(args.start_date) if args.start_date else None
    user_end = parse_iso_date(args.end_date) if args.end_date else None
    market_open_time = parse_iso_time(args.market_open_time)
    if user_start and user_end and user_start > user_end:
        raise ValueError("start-date must be on or before end-date")

    sync_script = Path(__file__).resolve().parent / "upstox_options_sync.py"
    if not sync_script.exists():
        raise FileNotFoundError(f"Missing sync script: {sync_script}")

    try:
        all_trading_days = await load_trading_days(args.underlying_symbol, market_open_time)
        filtered_days = [
            trade_day
            for trade_day in all_trading_days
            if (user_start is None or trade_day >= user_start)
            and (user_end is None or trade_day <= user_end)
        ]

        if not filtered_days:
            print("No trading days found for the selected filters.")
            return

        day_chunks = chunked_dates(filtered_days, args.chunk_trading_days)
        print(
            f"Found {len(filtered_days)} trading days. Running {len(day_chunks)} chunk(s) "
            f"with chunk size {args.chunk_trading_days}."
        )

        for index, day_chunk in enumerate(day_chunks, start=1):
            chunk_start = day_chunk[0]
            chunk_end = day_chunk[-1]
            command = build_sync_command(
                sync_script,
                chunk_start,
                chunk_end,
                args.underlying_symbol,
                args.max_expiries_per_day,
                args.dry_run,
                args.verbose,
            )
            print(
                f"[{index}/{len(day_chunks)}] Running {chunk_start.isoformat()} -> {chunk_end.isoformat()}"
            )
            subprocess.run(command, check=True)

        print("All chunks completed successfully.")
    finally:
        await DatabaseManager.close_pool()


if __name__ == "__main__":
    asyncio.run(async_main())
