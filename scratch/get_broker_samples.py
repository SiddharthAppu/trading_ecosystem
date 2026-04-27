import asyncio
import sys
from pathlib import Path
import json

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR / "packages" / "trading_core"))

from trading_core.db import DatabaseManager

BROKER_TABLES = [
    "broker_upstox.options_ohlc",
    "broker_upstox.options_greeks_live",
    "broker_fyers.market_ticks",
    "broker_fyers.options_greeks_live"
]

async def get_broker_table_info():
    pool = await DatabaseManager.get_pool()
    info = {}
    
    async with pool.acquire() as conn:
        for table in BROKER_TABLES:
            schema, name = table.split('.')
            
            # Get columns
            col_query = f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = '{schema}' AND table_name = '{name}' 
                ORDER BY ordinal_position;
            """
            cols = await conn.fetch(col_query)
            
            # Get sample rows (1 row)
            sample_query = f"SELECT * FROM {table} LIMIT 1;"
            try:
                samples = await conn.fetch(sample_query)
                sample_data = [dict(r) for r in samples]
            except Exception as e:
                sample_data = f"Error fetching samples: {e}"
            
            info[table] = {
                "columns": [dict(c) for c in cols],
                "samples": sample_data
            }
            
    print(json.dumps(info, indent=2, default=str))
    await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(get_broker_table_info())
