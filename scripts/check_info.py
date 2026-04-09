import asyncio
from trading_core.db import DatabaseManager

async def run():
    pool = await DatabaseManager.get_pool()
    schemas = await pool.fetch("SELECT schema_name FROM information_schema.schemata")
    print('Schemas:', [s['schema_name'] for s in schemas])
    
    tables = await pool.fetch("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')")
    print('Tables:')
    for t in tables:
        schema = t['table_schema']
        name = t['table_name']
        count = await pool.fetchval(f"SELECT count(*) FROM {schema}.{name}")
        print(f"  {schema}.{name}: {count} rows")
            
    await pool.close()

asyncio.run(run())
