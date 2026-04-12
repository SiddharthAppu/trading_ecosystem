import os
import sys
import argparse
import asyncio
from pathlib import Path
from datetime import datetime, timezone

# Path fix for monorepo imports
sys.path.append(str(Path(__file__).parent.parent / "packages" / "trading_core"))

from trading_core import get_adapter, AuthManager, DatabaseManager

async def main():
    parser = argparse.ArgumentParser(description="Quick OHLC Data Downloader (CLI)")
    parser.add_argument("--symbol", required=True, help="Symbol (e.g. NSE:NIFTY50-INDEX)")
    parser.add_argument("--start", required=True, help="Start Date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End Date (YYYY-MM-DD)")
    parser.add_argument("--provider", default="fyers", choices=["fyers", "upstox"])
    parser.add_argument("--resolution", default="1", help="Resolution (1, 1D, etc)")
    parser.add_argument("--no-db", action="store_true", help="Skip database saving")
    
    args = parser.parse_args()
    
    print(f"=== 📥 QUICK DOWNLOAD: {args.symbol} [{args.provider.upper()}] ===")
    
    try:
        # 1. Get Authenticated Adapter
        adapter = get_adapter(args.provider)
        if not adapter.validate_token():
            print(f"[ERROR] Session expired for {args.provider}. Run scripts/verify_auth.py or scripts/authenticate.py")
            return

        # 2. Fetch Data
        print(f"[*] Fetching {args.resolution}m data from {args.start} to {args.end}...")
        data = adapter.get_historical_data(args.symbol, args.start, args.end, args.resolution)
        
        if not data:
            print("[WARNING] No data returned from provider.")
            return
            
        print(f"[SUCCESS] Received {len(data)} candles.")

        # 3. Smart Table Detection
        table_name = "ohlcv_1m"
        # If it contains CE or PE, it's an option
        if "CE" in args.symbol or "PE" in args.symbol:
            table_name = "options_ohlc"
        
        full_table = f"broker_{args.provider}.{table_name}"

        # 4. Save to DB
        if not args.no_db:
            print(f"[*] Saving to Database table: {full_table}...")
            pool = await DatabaseManager.get_pool()
            async with pool.acquire() as conn:
                # Fyers format: [timestamp, open, high, low, close, volume]
                # Upstox format: [timestamp, open, high, low, close, volume] (standardized in core)
                
                # We need to map timestamps to datetime objects for TimescaleDB
                records = []
                for c in data:
                    ts = c[0]
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    records.append((dt, args.symbol, c[1], c[2], c[3], c[4], c[5]))
                
                query = f"""
                    INSERT INTO {full_table} (time, symbol, open, high, low, close, volume)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (time, symbol) DO UPDATE SET
                    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close, volume=EXCLUDED.volume
                """
                
                # Chunk insertion to prevent DB freeze/OOM on massive queries
                chunk_size = 1000
                total_records = len(records)
                print(f"[*] Starting batched database insertion ({chunk_size} rows/batch)...")
                
                for i in range(0, total_records, chunk_size):
                    batch = records[i:i + chunk_size]
                    await conn.executemany(query, batch)
                    print(f"  -> Inserted {min(i + chunk_size, total_records)} / {total_records} records...")
                
            print(f"\n[SUCCESS] {total_records} records successfully persisted.")
        else:
            print("[INFO] Database saving skipped (--no-db used).")

        # 5. Preview
        print("\nPreview:")
        for candle in data[:5]:
            print(f"  {candle}")
            
    except Exception as e:
        print(f"[CRITICAL ERROR] {str(e)}")
    finally:
        await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(main())
