import argparse
import asyncio
from datetime import date, datetime, time, timedelta, timezone
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT / "packages" / "trading_core"))

from trading_core.db import DatabaseManager  # noqa: E402


PROVIDER_SCHEMAS = {
    "fyers": "broker_fyers",
    "upstox": "broker_upstox",
}
IST = timezone(timedelta(hours=5, minutes=30))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate market_ticks into provider.ohlcv_1min_from_ticks for a single day."
    )
    parser.add_argument(
        "--provider",
        choices=["fyers", "upstox", "all"],
        default="all",
        help="Provider to aggregate for.",
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Target IST trade date in YYYY-MM-DD format to aggregate.",
    )
    parser.add_argument(
        "--symbols",
        default="",
        help="Optional comma-separated symbols filter.",
    )
    return parser.parse_args()


def parse_target_day(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("--date must be in YYYY-MM-DD format") from exc


def parse_symbols(value: str) -> list[str]:
    symbols = [s.strip() for s in value.split(",") if s.strip()]
    seen = set()
    deduped = []
    for s in symbols:
        if s not in seen:
            deduped.append(s)
            seen.add(s)
    return deduped


async def aggregate_provider(
    provider: str,
    day: date,
    symbols: list[str],
) -> None:
    schema = PROVIDER_SCHEMAS[provider]
    source_table = f"{schema}.market_ticks"
    target_table = f"{schema}.ohlcv_1min_from_ticks"

    ist_start = datetime.combine(day, time.min, tzinfo=IST)
    start_dt = ist_start.astimezone(timezone.utc)
    end_dt = start_dt + timedelta(days=1)

    print(f"\n[AGG] Provider={provider} Day={day.isoformat()} Target={target_table}")

    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            params = [start_dt, end_dt]
            symbol_filter = ""
            if symbols:
                params.append(symbols)
                symbol_filter = f" AND symbol = ANY(${len(params)}::text[])"

            delete_sql = (
                f"DELETE FROM {target_table} WHERE time >= $1 AND time < $2{symbol_filter};"
            )
            delete_result = await conn.execute(delete_sql, *params)
            print(f"[AGG] Cleared existing target rows: {delete_result}")

            insert_sql = f"""
                INSERT INTO {target_table} (
                    time, symbol, open, high, low, close, volume,
                    source_table, aggregation_timeframe, aggregation_run_at
                )
                SELECT
                    bucket_time AS time,
                    symbol,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    'market_ticks' AS source_table,
                    '1m' AS aggregation_timeframe,
                    NOW() AS aggregation_run_at
                FROM (
                    SELECT
                        time_bucket(INTERVAL '1 minute', time) AS bucket_time,
                        symbol,
                        (array_agg(price ORDER BY time ASC))[1] AS open,
                        MAX(price) AS high,
                        MIN(price) AS low,
                        (array_agg(price ORDER BY time DESC))[1] AS close,
                        COALESCE(SUM(volume), 0)::bigint AS volume
                    FROM {source_table}
                    WHERE time >= $1 AND time < $2{symbol_filter}
                    GROUP BY 1, 2
                ) bucketed
                ORDER BY time, symbol;
            """
            insert_result = await conn.execute(insert_sql, *params)
            print(f"[AGG] Inserted aggregated rows: {insert_result}")

            count_sql = (
                f"SELECT COUNT(*)::bigint FROM {target_table} "
                f"WHERE time >= $1 AND time < $2{symbol_filter};"
            )
            count = await conn.fetchval(count_sql, *params)
            print(f"[AGG] Final row count in target window: {count}")


async def main_async() -> None:
    args = parse_args()
    day = parse_target_day(args.date)
    symbols = parse_symbols(args.symbols)

    providers = ["fyers", "upstox"] if args.provider == "all" else [args.provider]
    for provider in providers:
        await aggregate_provider(provider, day, symbols)

    await DatabaseManager.close_pool()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
