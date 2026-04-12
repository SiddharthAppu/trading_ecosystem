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
    parser = argparse.ArgumentParser(description="Quick Option Chain Discoverer & Downloader (CLI)")
    parser.add_argument("--underlying", default="NSE:NIFTY50-INDEX", help="Underlying Symbol")
    parser.add_argument("--expiry", required=True, help="Expiry Date Part (e.g., 26MAR for Fyers, 2026-03-26 for Upstox)")
    parser.add_argument("--start", required=True, help="Start Date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End Date (YYYY-MM-DD)")
    parser.add_argument("--provider", default="fyers", choices=["fyers", "upstox"])
    parser.add_argument("--strike-count", type=int, default=10, help="Number of strikes to either side of ATM")
    parser.add_argument("--no-db", action="store_true", help="Skip database saving")
    
    args = parser.parse_args()
    
    print(f"=== 🧬 QUICK OPTION CHAIN: {args.underlying} [{args.provider.upper()}] ===")
    
    try:
        # 1. Get Authenticated Adapter
        adapter = get_adapter(args.provider)
        if not adapter.validate_token():
            print(f"[ERROR] Session expired for {args.provider}. Run scripts/verify_auth.py or scripts/authenticate.py")
            return

        # 2. Discover Chain
        print(f"[*] Discovering option chain for {args.underlying} at {args.expiry}...")
        results = adapter.get_option_chain_symbols(args.underlying, args.expiry, args.strike_count)
        
        atm = results.get("atm")
        spot = results.get("spot")
        symbols = results.get("symbols", [])
        
        if not symbols:
            print("[WARNING] No symbols discovered for expiry.")
            return

        print(f"[SUCCESS] ATM: {atm}, Spot Price: {spot}")
        print(f"[SUCCESS] Discovered {len(symbols)} symbols in chain.")

        # 3. Batch Download & Save
        full_table = f"broker_{args.provider}.options_ohlc"
        print(f"\n[*] Starting batch download and save to {full_table}...")
        
        total = len(symbols)
        pool = await DatabaseManager.get_pool()
        
        for i, sym in enumerate(symbols):
            print(f"  [{i+1}/{total}] Processing {sym}...", end="", flush=True)
            data = adapter.get_historical_data(sym, args.start, args.end)
            
            if data and not args.no_db:
                async with pool.acquire() as conn:
                    records = []
                    for c in data:
                        dt = datetime.fromtimestamp(c[0], tz=timezone.utc)
                        records.append((dt, sym, c[1], c[2], c[3], c[4], c[5]))
                    
                    query = f"""
                        INSERT INTO {full_table} (time, symbol, open, high, low, close, volume)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (time, symbol) DO UPDATE SET
                        open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close, volume=EXCLUDED.volume
                    """
                    await conn.executemany(query, records)
                print(f" -> {len(data)} saved.")
            elif data:
                print(f" -> {len(data)} received (no-db).")
            else:
                print(" -> [WARN] No data.")

        print("\n[SUCCESS] Batch operation completed.")

    except Exception as e:
        print(f"[CRITICAL ERROR] {str(e)}")
    finally:
        await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(main())
