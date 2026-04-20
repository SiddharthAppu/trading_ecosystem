import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
TRADING_CORE_DIR = ROOT_DIR / "packages" / "trading_core"
if str(TRADING_CORE_DIR) not in sys.path:
    sys.path.append(str(TRADING_CORE_DIR))

from trading_core.db import DatabaseManager

async def check_stats():
    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT count(*) FROM broker_upstox.options_ohlc")
        populated = await conn.fetchval("SELECT count(*) FROM broker_upstox.options_ohlc WHERE instrument_key IS NOT NULL")
        print(f"Total rows in database: {total}")
        print(f"Rows with populated instrument_key: {populated}")
        
    await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(check_stats())
