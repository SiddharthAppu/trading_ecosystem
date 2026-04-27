import asyncio
import sys
from pathlib import Path
import json

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT_DIR / "packages" / "trading_core"))

from trading_core.db import DatabaseManager

TABLES = [
    "master_broker.symbol_master",
    "master_broker.ohlcv_1m",
    "master_broker.options_ohlc_1m_fromupstox",
    "broker_upstox.market_ticks",
    "broker_upstox.options_greeks_live"
]

async def get_table_info():
    pool = await DatabaseManager.get_pool()
    info = {}
    
    async with pool.acquire() as conn:
        for table in TABLES:
            schema, name = table.split('.')
            
            # Get columns
            col_query = f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = '{schema}' AND table_name = '{name}' 
                ORDER BY ordinal_position;
            """
            cols = await conn.fetch(col_query)
            
            # Get sample rows (2 rows)
            sample_query = f"SELECT * FROM {table} LIMIT 2;"
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
    asyncio.run(get_table_info())
