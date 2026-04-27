import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR / "packages" / "trading_core"))

from trading_core.db import DatabaseManager

async def check_columns():
    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        for table in ['broker_upstox.options_ohlc', 'broker_upstox.ohlcv_1min_from_ticks']:
            print(f"\nColumns for {table}:")
            query = f"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = '{table.split('.')[0]}' AND table_name = '{table.split('.')[1]}' ORDER BY ordinal_position;"
            rows = await conn.fetch(query)
            for row in rows:
                print(f"  {row['column_name']} ({row['data_type']})")

    await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(check_columns())
