import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
TRADING_CORE_DIR = ROOT_DIR / "packages" / "trading_core"
if str(TRADING_CORE_DIR) not in sys.path:
    sys.path.append(str(TRADING_CORE_DIR))

from trading_core.db import DatabaseManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge provider live Greeks into analytics.options_greeks_master for a target date."
    )
    parser.add_argument(
        "--date",
        help="Target date in YYYY-MM-DD (default: previous day, IST).",
    )
    return parser.parse_args()


def resolve_target_date(raw_date: str | None) -> date:
    if raw_date:
        return datetime.strptime(raw_date, "%Y-%m-%d").date()
    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    return (ist_now - timedelta(days=1)).date()


async def merge_for_provider(conn, provider: str, target_date: date) -> str:
    source_table = f"broker_{provider}.options_greeks_live"
    query = f"""
        INSERT INTO analytics.options_greeks_master (provider, time, symbol, delta, theta, gamma, vega, iv)
        SELECT $1, time, symbol, delta, theta, gamma, vega, iv
        FROM {source_table}
        WHERE (time AT TIME ZONE 'Asia/Kolkata')::date = $2
        ON CONFLICT (provider, time, symbol) DO UPDATE SET
            delta = EXCLUDED.delta,
            theta = EXCLUDED.theta,
            gamma = EXCLUDED.gamma,
            vega = EXCLUDED.vega,
            iv = EXCLUDED.iv
    """
    await conn.execute(query, provider, target_date)

    count_query = f"SELECT COUNT(*) FROM {source_table} WHERE (time AT TIME ZONE 'Asia/Kolkata')::date = $1"
    count = await conn.fetchval(count_query, target_date)
    return f"{provider}: merged {count} rows for {target_date}"


async def ensure_master_table(conn) -> None:
    await conn.execute(
        """
        CREATE SCHEMA IF NOT EXISTS analytics;
        CREATE TABLE IF NOT EXISTS analytics.options_greeks_master (
            provider TEXT NOT NULL,
            time TIMESTAMPTZ NOT NULL,
            symbol TEXT NOT NULL,
            delta DOUBLE PRECISION,
            theta DOUBLE PRECISION,
            gamma DOUBLE PRECISION,
            vega DOUBLE PRECISION,
            iv DOUBLE PRECISION,
            UNIQUE(provider, time, symbol)
        );
        SELECT create_hypertable('analytics.options_greeks_master', 'time', if_not_exists => TRUE);
        """
    )


async def main_async() -> None:
    args = parse_args()
    target_date = resolve_target_date(args.date)

    pool = await DatabaseManager.get_pool()
    try:
        async with pool.acquire() as conn:
            await ensure_master_table(conn)
            messages = []
            for provider in ("upstox", "fyers"):
                try:
                    msg = await merge_for_provider(conn, provider, target_date)
                except Exception as exc:
                    msg = f"{provider}: skipped ({exc})"
                messages.append(msg)

        print("\n".join(messages))
    finally:
        await DatabaseManager.close_pool()


if __name__ == "__main__":
    asyncio.run(main_async())
