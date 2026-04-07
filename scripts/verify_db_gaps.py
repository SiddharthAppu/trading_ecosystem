import asyncio
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add core package to path
sys.path.append(str(Path(__file__).parent.parent / "packages" / "trading_core"))
from trading_core.db import DatabaseManager

async def check_gaps():
    print("=== TRADING DB CONTINUITY SCANNER ===")
    pool = await DatabaseManager.get_pool()
    
    tables = [
        "broker_fyers.ohlcv_1m",
        "broker_upstox.ohlcv_1m",
        "broker_fyers.options_ohlc",
        "broker_upstox.options_ohlc",
        "broker_fyers.market_ticks",
        "broker_upstox.market_ticks"
    ]
    
    async with pool.acquire() as conn:
        for table in tables:
            try:
                # Check total rows
                count_query = f"SELECT COUNT(*) FROM {table};"
                count = await conn.fetchval(count_query)
                
                if count == 0:
                    print(f"\n[TABLE] {table}: EMPTY")
                    continue
                
                print(f"\n[TABLE] {table}: {count} records found.")
                
                # Check min and max dates per symbol
                bounds_query = f"""
                    SELECT symbol,
                           MIN(time) as min_time,
                           MAX(time) as max_time,
                           COUNT(*) as total_records
                    FROM {table}
                    GROUP BY symbol;
                """
                
                symbols = await conn.fetch(bounds_query)
                for sym in symbols:
                    s_name = sym['symbol']
                    min_t = sym['min_time']
                    max_t = sym['max_time']
                    records = sym['total_records']
                    
                    print(f"  -> Symbol: {s_name}")
                    print(f"     Range: {min_t} TO {max_t}")
                    
                    # For 1m data, we can approximate missing days. 
                    # A perfect 1m table (375 mins per day)
                    days_diff = (max_t.date() - min_t.date()).days
                    if days_diff > 0:
                        expected_mins = days_diff * (375*5/7) # approx trading days
                        health = min(int((records / expected_mins) * 100) if expected_mins else 100, 100)
                        print(f"     Continuity Health: ~{health}% (Records: {records})")
                    else:
                        print(f"     Continuity Health: Single day data.")
                        
            except Exception as e:
                # Table might not exist or be corrupted
                pass

    await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(check_gaps())
