import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR / "packages" / "trading_core"))

from trading_core.db import DatabaseManager

async def list_tables():
    pool = await DatabaseManager.get_pool()
    query = """
        SELECT table_schema, table_name 
        FROM information_schema.tables 
        WHERE table_schema IN ('broker_upstox', 'broker_fyers', 'master_broker')
        ORDER BY table_schema, table_name;
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        for row in rows:
            print(f"{row['table_schema']}.{row['table_name']}")

    await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(list_tables())
