"""Check broker_upstox and broker_fyers schemas for tick data availability."""
import asyncio
from dotenv import dotenv_values
import asyncpg

cfg = dotenv_values("config/.env")
db_url = (
    cfg.get("DATABASE_URL")
    or "postgresql://{}:{}@{}:{}/{}".format(
        cfg["DB_USER"], cfg["DB_PASSWORD"], cfg["DB_HOST"],
        cfg.get("DB_PORT", 5432), cfg["DB_NAME"]
    )
)

NIFTY_INDEX = "NSE:NIFTY50-INDEX"

async def main():
    pool = await asyncpg.create_pool(db_url)
    async with pool.acquire() as c:
        # List tables in each schema
        for schema in ("broker_upstox", "broker_fyers", "master_broker"):
            rows = await c.fetch(
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema='{schema}' ORDER BY table_name"
            )
            print(f"\n{schema} tables: {[r['table_name'] for r in rows]}")

        # Check broker_upstox.market_ticks if it exists
        exists = await c.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='broker_upstox' AND table_name='market_ticks')"
        )
        print(f"\nbroker_upstox.market_ticks exists: {exists}")
        if exists:
            cols = await c.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='broker_upstox' AND table_name='market_ticks' "
                "ORDER BY ordinal_position"
            )
            print(f"  columns: {[r['column_name'] for r in cols]}")
            ts_col = cols[0]["column_name"]
            # Coverage
            rows = await c.fetch(
                f"SELECT DATE({ts_col}) AS day, COUNT(*) AS cnt "
                f"FROM broker_upstox.market_ticks "
                f"GROUP BY DATE({ts_col}) ORDER BY day DESC LIMIT 15"
            )
            print("  coverage (all symbols):")
            for r in rows:
                print(f"    {dict(r)}")
            # Check for NIFTY index specifically
            rows2 = await c.fetch(
                f"SELECT DATE({ts_col}) AS day, COUNT(*) AS cnt "
                f"FROM broker_upstox.market_ticks WHERE symbol=$1 "
                f"GROUP BY DATE({ts_col}) ORDER BY day DESC LIMIT 15",
                NIFTY_INDEX
            )
            print(f"  NIFTY50-INDEX rows: {[dict(r) for r in rows2]}")
            # Distinct symbols sample
            syms = await c.fetch(
                "SELECT DISTINCT symbol FROM broker_upstox.market_ticks ORDER BY symbol LIMIT 20"
            )
            print(f"  sample symbols: {[r['symbol'] for r in syms]}")

        # broker_fyers.market_ticks NIFTY50 index check
        print(f"\nbroker_fyers.market_ticks — NIFTY50-INDEX rows:")
        rows = await c.fetch(
            "SELECT DATE(time) AS day, COUNT(*) AS cnt "
            "FROM broker_fyers.market_ticks WHERE symbol=$1 "
            "GROUP BY DATE(time) ORDER BY day DESC LIMIT 15",
            NIFTY_INDEX
        )
        if rows:
            for r in rows: print(f"  {dict(r)}")
        else:
            print("  (no rows for NSE:NIFTY50-INDEX)")

        # broker_fyers.market_ticks options coverage
        print("\nbroker_fyers.market_ticks — options coverage (recent days):")
        rows = await c.fetch(
            "SELECT DATE(time) AS day, COUNT(*) AS cnt, "
            "COUNT(DISTINCT symbol) AS distinct_syms "
            "FROM broker_fyers.market_ticks "
            "GROUP BY DATE(time) ORDER BY day DESC LIMIT 10"
        )
        for r in rows: print(f"  {dict(r)}")

    await pool.close()

asyncio.run(main())
