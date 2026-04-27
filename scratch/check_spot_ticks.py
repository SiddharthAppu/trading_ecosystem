import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR / "packages" / "trading_core"))

from trading_core.db import DatabaseManager

async def check_spot():
    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        fyers_count = await conn.fetchval(
            "SELECT COUNT(*) FROM broker_fyers.market_ticks WHERE symbol = 'NSE:NIFTY50-INDEX'"
        )
        upstox_count = await conn.fetchval(
            "SELECT COUNT(*) FROM broker_upstox.market_ticks WHERE symbol = 'NSE_INDEX|Nifty 50'"
        )
        print(f"Fyers Spot Ticks (NSE:NIFTY50-INDEX): {fyers_count}")
        print(f"Upstox Spot Ticks (NSE_INDEX|Nifty 50): {upstox_count}")

    await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(check_spot())
