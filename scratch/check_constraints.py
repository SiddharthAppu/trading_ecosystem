import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR / "packages" / "trading_core"))

from trading_core.db import DatabaseManager

async def check_constraints():
    pool = await DatabaseManager.get_pool()
    query = """
        SELECT conname, pg_get_constraintdef(c.oid) 
        FROM pg_constraint c 
        JOIN pg_namespace n ON n.oid = c.connamespace 
        WHERE n.nspname = 'master_broker' AND conrelid = 'master_broker.ohlcv_1m'::regclass;
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        for row in rows:
            print(f"Constraint: {row['conname']} -> {row['pg_get_constraintdef']}")
        
        if not rows:
            print("No constraints found.")

    await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(check_constraints())
