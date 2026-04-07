import asyncio
import asyncpg
import logging
from trading_core.db import MigrationManager, DatabaseManager

async def reset():
    print("=== NUKING DB SCHEMAS ===")
    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA IF EXISTS broker_fyers CASCADE;")
        await conn.execute("DROP SCHEMA IF EXISTS broker_upstox CASCADE;")
        await conn.execute("DROP SCHEMA IF EXISTS analytics CASCADE;")
    print("[SUCCESS] Schemas dropped.")
    await MigrationManager.run_migrations()
    print("[SUCCESS] DB Reset.")
    await DatabaseManager.close_pool()

asyncio.run(reset())
