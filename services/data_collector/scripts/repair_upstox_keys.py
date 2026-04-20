import asyncio
import logging
import sys
from pathlib import Path
from datetime import date

ROOT_DIR = Path(__file__).resolve().parents[3]
TRADING_CORE_DIR = ROOT_DIR / "packages" / "trading_core"
if str(TRADING_CORE_DIR) not in sys.path:
    sys.path.append(str(TRADING_CORE_DIR))

from trading_core.db import DatabaseManager
from trading_core.providers.upstox_historical import UpstoxHistoricalDataFetcher
from trading_core.providers.upstox_adapter import UPSTOX_UNDERLYING_KEYS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("upstox_repair")

async def repair_keys(underlying_symbol: str = "NSE:NIFTY50-INDEX"):
    fetcher = UpstoxHistoricalDataFetcher()
    underlying_key = UPSTOX_UNDERLYING_KEYS.get(underlying_symbol, underlying_symbol)
    
    logger.info(f"Fetching all expired expiries for {underlying_symbol}...")
    raw_expiries = await fetcher.get_expired_expiries(underlying_key)
    
    # Extract just the date strings
    expiries = []
    for item in raw_expiries:
        if isinstance(item, str): expiries.append(item[:10])
        elif isinstance(item, dict): expiries.append(str(item.get("expiry") or item.get("date"))[:10])
    
    logger.info(f"Found {len(expiries)} historical expiries. Building global symbol mapping...")
    
    symbol_to_key_map = {}
    
    # Fetch contracts for each expiry to build a master lookup
    for i, expiry in enumerate(expiries):
        try:
            logger.info(f"[{i+1}/{len(expiries)}] Fetching contracts for expiry {expiry}...")
            contracts = await fetcher.get_expired_option_contracts_batch(underlying_key, expiry)
            
            for contract in contracts:
                t_symbol = contract.get("trading_symbol")
                i_key = contract.get("instrument_key")
                if t_symbol and i_key:
                    symbol_to_key_map[t_symbol] = i_key
            
            # Be gentle on the metadata API
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Failed to fetch contracts for {expiry}: {e}")

    logger.info(f"Metadata collection complete. Mapped {len(symbol_to_key_map)} unique symbols.")
    
    pool = await DatabaseManager.get_pool()
    total_updated = 0
    
    # Now run updates in batches of symbols
    all_symbols = list(symbol_to_key_map.keys())
    batch_size = 50
    
    logger.info("Starting database updates...")
    
    async with pool.acquire() as conn:
        for i in range(0, len(all_symbols), batch_size):
            chunk = all_symbols[i:i + batch_size]
            
            # Update query
            # We update all rows matching the symbol where instrument_key is currently null
            for symbol in chunk:
                key = symbol_to_key_map[symbol]
                res = await conn.execute(
                    "UPDATE broker_upstox.options_ohlc SET instrument_key = $1 WHERE symbol = $2 AND instrument_key IS NULL",
                    key, symbol
                )
                # Parse count from response string like 'UPDATE 1234'
                count = int(res.split(" ")[1])
                total_updated += count
            
            if i % 250 == 0:
                logger.info(f"Progress: Processed {i} symbols... {total_updated} rows updated so far.")

    logger.info(f"Repair complete! Total rows updated with instrument_key: {total_updated}")
    await DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(repair_keys())
