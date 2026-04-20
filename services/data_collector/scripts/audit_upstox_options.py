import argparse
import asyncio
import logging
import random
from datetime import datetime
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]
TRADING_CORE_DIR = ROOT_DIR / "packages" / "trading_core"

if str(TRADING_CORE_DIR) not in sys.path:
    sys.path.append(str(TRADING_CORE_DIR))

from trading_core.db import DatabaseManager
from trading_core.providers.upstox_historical import UpstoxHistoricalDataFetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("upstox_audit")

async def get_random_samples(limit: int):
    pool = await DatabaseManager.get_pool()
    query = """
        SELECT * FROM (
            SELECT DISTINCT time::date as trade_date, symbol, instrument_key
            FROM broker_upstox.options_ohlc
            WHERE instrument_key IS NOT NULL
        ) sub
        ORDER BY random()
        LIMIT $1
    """
    async with pool.acquire() as connection:
        records = await connection.fetch(query, limit)
        return [(r["trade_date"], r["symbol"], r["instrument_key"]) for r in records]

async def count_db_candles(trade_date, symbol):
    pool = await DatabaseManager.get_pool()
    query = """
        SELECT COUNT(*) 
        FROM broker_upstox.options_ohlc 
        WHERE symbol = $1 AND time::date = $2
    """
    async with pool.acquire() as connection:
        return await connection.fetchval(query, symbol, trade_date)

async def run_audit(samples: int):
    logger.info("Initializing Upstox API fetcher for Audit...")
    fetcher = UpstoxHistoricalDataFetcher()
    
    logger.info(f"Selecting {samples} random trading days & symbols from database...")
    targets = await get_random_samples(samples)
    
    if not targets:
        logger.warning("No data found in broker_upstox.options_ohlc to audit.")
        return

    mismatches = 0
    for trade_date, symbol, instrument_key in targets:
        # Re-fetch exactly using the stored key
        date_str = trade_date.isoformat()
        
        logger.info(f"--- Auditing {symbol} on {date_str} ---")
        
        # 1. Fetch DB candle count
        db_count = await count_db_candles(trade_date, symbol)
        
        # 2. Re-download from Upstox
        logger.info(f"Re-downloading {instrument_key} from Upstox API...")
        results = await fetcher.download_historical_candles_batch([instrument_key], date_str, date_str)
        
        api_count = 0
        if results and not isinstance(results[0], Exception):
            api_count = len(results[0].get("candles", []))
            
        # 3. Compare Results
        if db_count == api_count:
            logger.info(f"✅ MATCH: DB has {db_count} rows, API returned {api_count} rows.")
        else:
            logger.error(f"❌ MISMATCH: DB holds {db_count} rows, API returned {api_count} rows!")
            mismatches += 1
            
        await asyncio.sleep(2) # be gentle with the API
            
    await DatabaseManager.close_pool()
    
    if mismatches > 0:
        logger.error(f"Audit Complete. Found {mismatches} mismatches out of {samples} samples audited.")
    else:
        logger.info(f"Audit Complete. Perfect match across all {samples} random samples.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Randomly audit downloaded options data against the live Upstox API.")
    parser.add_argument("--samples", type=int, default=5, help="Number of random date/contract pairs to check.")
    args = parser.parse_args()
    
    asyncio.run(run_audit(args.samples))
