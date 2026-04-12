import argparse
import asyncio
from datetime import datetime, time, timedelta, timezone
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT / "packages" / "trading_core"))

from trading_core.db import DatabaseManager  # noqa: E402


PROVIDER_SCHEMAS = {
    "fyers": "broker_fyers",
    "upstox": "broker_upstox",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate derived ohlcv_1min_from_ticks vs direct tick aggregation."
    )
    parser.add_argument("--provider", choices=["fyers", "upstox"], default="fyers")
    parser.add_argument("--date", required=True, help="UTC date in YYYY-MM-DD format")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-9,
        help="Numeric tolerance for OHLC comparisons",
    )
    return parser.parse_args()


def parse_target_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("--date must be in YYYY-MM-DD format") from exc


async def main_async() -> None:
    args = parse_args()
    target_day = parse_target_date(args.date)
    schema = PROVIDER_SCHEMAS[args.provider]

    start_dt = datetime.combine(target_day, time.min, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)

    source_table = f"{schema}.market_ticks"
    target_table = f"{schema}.ohlcv_1min_from_ticks"

    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        summary = await conn.fetchrow(
            f"""
            WITH expected AS (
                SELECT
                    time_bucket(INTERVAL '1 minute', time) AS bucket_time,
                    symbol,
                    (array_agg(price ORDER BY time ASC))[1] AS open,
                    MAX(price) AS high,
                    MIN(price) AS low,
                    (array_agg(price ORDER BY time DESC))[1] AS close,
                    COALESCE(SUM(volume), 0)::bigint AS volume
                FROM {source_table}
                WHERE time >= $1 AND time < $2
                GROUP BY 1, 2
            ),
            actual AS (
                SELECT time, symbol, open, high, low, close, volume
                FROM {target_table}
                WHERE time >= $1 AND time < $2
            ),
            joined AS (
                SELECT
                    COALESCE(e.bucket_time, a.time) AS bucket_time,
                    COALESCE(e.symbol, a.symbol) AS symbol,
                    e.open AS e_open,
                    e.high AS e_high,
                    e.low AS e_low,
                    e.close AS e_close,
                    e.volume AS e_volume,
                    a.open AS a_open,
                    a.high AS a_high,
                    a.low AS a_low,
                    a.close AS a_close,
                    a.volume AS a_volume
                FROM expected e
                FULL OUTER JOIN actual a
                    ON e.bucket_time = a.time
                   AND e.symbol = a.symbol
            )
            SELECT
                (SELECT COUNT(*)::bigint FROM expected) AS expected_rows,
                (SELECT COUNT(*)::bigint FROM actual) AS actual_rows,
                COUNT(*) FILTER (WHERE e_open IS NOT NULL AND a_open IS NULL)::bigint AS missing_in_target,
                COUNT(*) FILTER (WHERE e_open IS NULL AND a_open IS NOT NULL)::bigint AS extra_in_target,
                COUNT(*) FILTER (
                    WHERE e_open IS NOT NULL
                      AND a_open IS NOT NULL
                      AND (
                        ABS(e_open - a_open) > $3
                        OR ABS(e_high - a_high) > $3
                        OR ABS(e_low - a_low) > $3
                        OR ABS(e_close - a_close) > $3
                        OR e_volume <> a_volume
                      )
                )::bigint AS mismatched_rows
            FROM joined;
            """,
            start_dt,
            end_dt,
            args.tolerance,
        )

        mismatches = await conn.fetch(
            f"""
            WITH expected AS (
                SELECT
                    time_bucket(INTERVAL '1 minute', time) AS bucket_time,
                    symbol,
                    (array_agg(price ORDER BY time ASC))[1] AS open,
                    MAX(price) AS high,
                    MIN(price) AS low,
                    (array_agg(price ORDER BY time DESC))[1] AS close,
                    COALESCE(SUM(volume), 0)::bigint AS volume
                FROM {source_table}
                WHERE time >= $1 AND time < $2
                GROUP BY 1, 2
            ),
            actual AS (
                SELECT time, symbol, open, high, low, close, volume
                FROM {target_table}
                WHERE time >= $1 AND time < $2
            )
            SELECT
                COALESCE(e.bucket_time, a.time) AS bucket_time,
                COALESCE(e.symbol, a.symbol) AS symbol,
                e.open AS expected_open,
                a.open AS actual_open,
                e.high AS expected_high,
                a.high AS actual_high,
                e.low AS expected_low,
                a.low AS actual_low,
                e.close AS expected_close,
                a.close AS actual_close,
                e.volume AS expected_volume,
                a.volume AS actual_volume
            FROM expected e
            FULL OUTER JOIN actual a
                ON e.bucket_time = a.time
               AND e.symbol = a.symbol
            WHERE
                (e.open IS NOT NULL AND a.open IS NULL)
                OR (e.open IS NULL AND a.open IS NOT NULL)
                OR (
                    e.open IS NOT NULL
                    AND a.open IS NOT NULL
                    AND (
                        ABS(e.open - a.open) > $3
                        OR ABS(e.high - a.high) > $3
                        OR ABS(e.low - a.low) > $3
                        OR ABS(e.close - a.close) > $3
                        OR e.volume <> a.volume
                    )
                )
            ORDER BY bucket_time, symbol
            LIMIT 10;
            """,
            start_dt,
            end_dt,
            args.tolerance,
        )

    print(
        "[VALIDATE] provider="
        f"{args.provider} date={target_day.isoformat()} "
        f"expected_rows={summary['expected_rows']} actual_rows={summary['actual_rows']}"
    )
    print(
        "[VALIDATE] missing_in_target="
        f"{summary['missing_in_target']} extra_in_target={summary['extra_in_target']} "
        f"mismatched_rows={summary['mismatched_rows']}"
    )

    if mismatches:
        print("[VALIDATE] sample mismatches (up to 10):")
        for row in mismatches:
            print(dict(row))

    if (
        summary["missing_in_target"] != 0
        or summary["extra_in_target"] != 0
        or summary["mismatched_rows"] != 0
    ):
        raise RuntimeError("Aggregation reconciliation failed")

    print("[VALIDATE] tick aggregation reconciliation passed.")
    await DatabaseManager.close_pool()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
