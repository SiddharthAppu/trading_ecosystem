import asyncio
import sys
from pathlib import Path
import json

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR / "packages" / "trading_core"))

from trading_core.db import DatabaseManager

THOROUGH_TABLES = [
    "broker_fyers.ohlcv_1m",
    "broker_upstox.ohlcv_1m",
    "master_broker.v_combined_ticks"
]

async def get_thorough_info():
    pool = await DatabaseManager.get_pool()
    info = {}
    
    async with pool.acquire() as conn:
        for table in THOROUGH_TABLES:
            schema, name = table.split('.')
            
            # Get columns
            col_query = f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = '{schema}' AND table_name = '{name}' 
                ORDER BY ordinal_position;
            """
            cols = await conn.fetch(col_query)
            
            # Check if it's a view
            view_query = f"SELECT table_type FROM information_schema.tables WHERE table_schema = '{schema}' AND table_name = '{name}';"
            table_type = await conn.fetchval(view_query)
            
            # Get sample rows (1 row)
            sample_query = f"SELECT * FROM {table} LIMIT 1;"
            try:
                samples = await conn.fetch(sample_query)
                sample_data = [dict(r) for r in samples]
            except Exception as e:
                sample_data = f"Error fetching samples: {e}"
            
            info[table] = {
                "type": table_type,
                "columns": [dict(c) for c in cols],
                "samples": sample_data
            }
            
    print(json.dumps(info, indent=2, default=str))
    await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(get_thorough_info())
