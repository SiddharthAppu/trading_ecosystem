import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect('postgresql://trading:trading@localhost:5432/trading_db')
    records = await conn.fetch("SELECT constraint_name, constraint_type FROM information_schema.table_constraints WHERE table_name = 'ohlcv_1m';")
    print([dict(r) for r in records])
    await conn.close()

asyncio.run(check())
