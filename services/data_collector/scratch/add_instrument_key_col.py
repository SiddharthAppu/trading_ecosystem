import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
TRADING_CORE_DIR = ROOT_DIR / "packages" / "trading_core"
if str(TRADING_CORE_DIR) not in sys.path:
    sys.path.append(str(TRADING_CORE_DIR))

from trading_core.db import DatabaseManager

async def upgrade_schema():
    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        print("Checking if 'instrument_key' column exists in broker_upstox.options_ohlc...")
        
        # Check if column exists
        col_exists = await conn.fetchval("""
            SELECT count(*) 
            FROM information_schema.columns 
            WHERE table_schema = 'broker_upstox' 
              AND table_name = 'options_ohlc' 
              AND column_name = 'instrument_key'
        """)
        
        if col_exists == 0:
            print("Adding 'instrument_key' column...")
            await conn.execute("ALTER TABLE broker_upstox.options_ohlc ADD COLUMN instrument_key VARCHAR(255)")
            print("Column added successfully.")
        else:
            print("Column 'instrument_key' already exists.")
            
    await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(upgrade_schema())
