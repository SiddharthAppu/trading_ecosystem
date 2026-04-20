import asyncio
import asyncpg
from datetime import datetime
from trading_core.providers.upstox_adapter import UpstoxAdapter

async def download_vix():
    adapter = UpstoxAdapter()
    if not adapter.validate_token():
        print("Error: Upstox token invalid. Please authenticate first.")
        return

    vix_key = "NSE_INDEX|India VIX"
    # Target period based on user data
    start_date = "2024-08-01"
    end_date = "2025-07-31"
    
    print(f"[*] Downloading India VIX historical data for {start_date} to {end_date}...")
    
    # get_historical_data returns [[ts, o, h, l, c, v], ...]
    data = adapter.get_historical_data(vix_key, start_date, end_date, "1")
    
    if not data:
        print("[!] No data returned for India VIX.")
        return

    print(f"[*] Fetched {len(data):,} candles. Saving to database...")
    
    conn = await asyncpg.connect("postgresql://trading:trading@localhost:5432/trading_db")
    
    # Prepare for batch insert
    # Table schema: time, symbol, open, high, low, close, volume
    records = [
        (datetime.fromtimestamp(row[0]), "NSE_INDEX|India VIX", row[1], row[2], row[3], row[4], int(row[5] or 0))
        for row in data
    ]
    
    try:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS broker_upstox;")
        # No need to create table, it should exist from migrations
        
        await conn.copy_records_to_table(
            "ohlcv_1m",
            records=records,
            columns=["time", "symbol", "open", "high", "low", "close", "volume"],
            schema_name="broker_upstox"
        )
        print(f"[SUCCESS] Saved {len(records):,} India VIX records to broker_upstox.ohlcv_1m")
    except Exception as e:
        print(f"[ERROR] Failed to save data: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(download_vix())
