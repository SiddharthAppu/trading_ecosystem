"""Check ohlcv_1min_from_ticks for NIFTY50 index data."""
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

async def main():
    pool = await asyncpg.create_pool(db_url)
    async with pool.acquire() as c:
        tests = [
            ("broker_fyers.ohlcv_1min_from_ticks", "NSE:NIFTY50-INDEX"),
            ("broker_upstox.ohlcv_1min_from_ticks", "NSE_INDEX|Nifty 50"),
            ("broker_upstox.ohlcv_1min_from_ticks", "NSE:NIFTY50-INDEX"),
        ]
        for table, sym in tests:
            try:
                rows = await c.fetch(
                    f"SELECT DATE(time) AS d, COUNT(*) AS cnt FROM {table} "
                    f"WHERE symbol=$1 GROUP BY DATE(time) ORDER BY d DESC LIMIT 10",
                    sym,
                )
                print(f"{table} ({sym}): {[dict(r) for r in rows]}")
            except Exception as e:
                print(f"{table} ({sym}): ERROR {e}")

        # Also check distinct symbols in each table
        for table in ("broker_fyers.ohlcv_1min_from_ticks", "broker_upstox.ohlcv_1min_from_ticks"):
            rows = await c.fetch(
                f"SELECT DISTINCT symbol FROM {table} WHERE symbol NOT LIKE '%CE' "
                f"AND symbol NOT LIKE '%PE' AND symbol NOT LIKE 'NSE_FO%' ORDER BY symbol LIMIT 10"
            )
            print(f"{table} non-option symbols: {[r['symbol'] for r in rows]}")

    await pool.close()

asyncio.run(main())
