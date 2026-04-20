import argparse
import asyncio
import logging
import math
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parents[3]
TRADING_CORE_DIR = ROOT_DIR / "packages" / "trading_core"

if str(TRADING_CORE_DIR) not in sys.path:
    sys.path.append(str(TRADING_CORE_DIR))

from trading_core.db import DatabaseManager
from trading_core.providers.upstox_adapter import UPSTOX_UNDERLYING_KEYS
from trading_core.providers.upstox_historical import UpstoxHistoricalDataFetcher

logger = logging.getLogger("upstox_options_sync")

DEFAULT_UNDERLYING_SYMBOL = "NSE:NIFTY50-INDEX"
DEFAULT_MARKET_OPEN_TIME = "09:15:00"
MARKET_OPEN_TIME = time.fromisoformat(DEFAULT_MARKET_OPEN_TIME)
STRIKE_STEP = 50
SIDE_STRIKE_COUNT = 21
TOTAL_SYMBOLS_PER_EXPIRY = (SIDE_STRIKE_COUNT * 2) + 1
DEFAULT_EXPIRY_WINDOW_DAYS = 35
UPSERT_BATCH_SIZE = 1000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Upstox expired option candles and upsert them into broker_upstox.options_ohlc."
    )
    parser.add_argument("--start-date", required=True, help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", required=True, help="End date in YYYY-MM-DD format.")
    parser.add_argument(
        "--underlying-symbol",
        default=DEFAULT_UNDERLYING_SYMBOL,
        help="Underlying spot symbol stored in broker_upstox.ohlcv_1m.",
    )
    parser.add_argument(
        "--expiry-window-days",
        type=int,
        default=DEFAULT_EXPIRY_WINDOW_DAYS,
        help="How many calendar days ahead to treat expiries as active for a trade date.",
    )
    parser.add_argument(
        "--max-expiries-per-day",
        type=int,
        default=0,
        help="Optional cap on active expiries per day. Use 0 for no cap.",
    )
    parser.add_argument(
        "--atm-option-type",
        choices=["CE", "PE"],
        default="CE",
        help="Instrument type to use for the single ATM contract in the 43-symbol set.",
    )
    parser.add_argument(
        "--limit-days",
        type=int,
        default=0,
        help="Optional limit for number of trading days processed after filtering.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve symbols and fetch metadata without downloading candles or writing to DB.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def normalize_expiry_values(raw_expiries: Iterable[object]) -> list[date]:
    expiries: set[date] = set()
    for item in raw_expiries:
        if isinstance(item, str):
            expiries.add(parse_iso_date(item[:10]))
            continue
        if isinstance(item, dict):
            for key in ("expiry", "expiry_date", "date"):
                value = item.get(key)
                if value:
                    expiries.add(parse_iso_date(str(value)[:10]))
                    break
    return sorted(expiries)


def round_to_strike(spot_price: float) -> int:
    return int(round(spot_price / STRIKE_STEP) * STRIKE_STEP)


def build_target_contract_specs(atm_strike: int, atm_option_type: str) -> list[tuple[int, str]]:
    specs: list[tuple[int, str]] = []
    for offset in range(SIDE_STRIKE_COUNT, 0, -1):
        specs.append((atm_strike - (offset * STRIKE_STEP), "PE"))
    specs.append((atm_strike, atm_option_type))
    for offset in range(1, SIDE_STRIKE_COUNT + 1):
        specs.append((atm_strike + (offset * STRIKE_STEP), "CE"))
    return specs


def select_active_expiries(
    trade_day: date,
    expiries: list[date],
    expiry_window_days: int,
    max_expiries_per_day: int,
) -> list[date]:
    window_end = trade_day + timedelta(days=expiry_window_days)
    active = [expiry for expiry in expiries if trade_day <= expiry <= window_end]
    if max_expiries_per_day > 0:
        return active[:max_expiries_per_day]
    return active


def extract_timestamp(candle_time: object) -> datetime:
    if isinstance(candle_time, datetime):
        return candle_time
    if not isinstance(candle_time, str):
        raise ValueError(f"Unsupported candle timestamp type: {type(candle_time)!r}")
    return datetime.fromisoformat(candle_time)


def chunked(values: list[tuple], chunk_size: int) -> Iterable[list[tuple]]:
    for index in range(0, len(values), chunk_size):
        yield values[index:index + chunk_size]


class UpstoxOptionsSync:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.fetcher = UpstoxHistoricalDataFetcher()
        self.underlying_key = UPSTOX_UNDERLYING_KEYS.get(args.underlying_symbol, args.underlying_symbol)

    async def run(self) -> None:
        if not self.fetcher.adapter.validate_token():
            raise ValueError("Upstox token is invalid. Run scripts/lib/authenticate.py or scripts/lib/verify_auth.py first.")

        start_date = parse_iso_date(self.args.start_date)
        end_date = parse_iso_date(self.args.end_date)
        if start_date > end_date:
            raise ValueError("start-date must be on or before end-date")

        raw_expiries = await self.fetcher.get_expired_expiries(self.underlying_key)
        expiries = normalize_expiry_values(raw_expiries)
        if not expiries:
            raise ValueError(f"No expired expiries returned for {self.underlying_key}")

        logger.info("Loaded %s historical expiries for %s", len(expiries), self.underlying_key)

        trading_days = await self._load_trading_days_with_spot(start_date, end_date)
        if self.args.limit_days > 0:
            trading_days = trading_days[: self.args.limit_days]

        if not trading_days:
            logger.warning("No trading days found in broker_upstox.ohlcv_1m for the requested window.")
            await DatabaseManager.close_pool()
            return

        total_rows = 0
        try:
            for trade_day, spot_open in trading_days:
                active_expiries = select_active_expiries(
                    trade_day,
                    expiries,
                    self.args.expiry_window_days,
                    self.args.max_expiries_per_day,
                )
                if not active_expiries:
                    logger.info("Skipping %s because no expiries fall within the active window.", trade_day)
                    continue

                rows_written = await self._process_trade_day(trade_day, spot_open, active_expiries)
                total_rows += rows_written
                
                # Small pause between days to avoid hitting rolling API limits
                if trade_day != trading_days[-1][0]:
                    await asyncio.sleep(1)
                    
            if not self.args.dry_run and total_rows > 0:
                await self._inline_audit()
                
        finally:
            await DatabaseManager.close_pool()

        logger.info("Sync complete. Upserted %s option candles.", total_rows)

    async def _load_trading_days_with_spot(self, start_date: date, end_date: date) -> list[tuple[date, float]]:
        pool = await DatabaseManager.get_pool()
        
        # We prefer Upstox spot but fallback to Fyers for older data (pre-2023)
        query = """
            WITH spot_data AS (
                SELECT time::date AS trade_day, open, 'upstox' as src
                FROM broker_upstox.ohlcv_1m
                WHERE symbol = $1
                  AND time::date BETWEEN $2 AND $3
                  AND time::time = $4::time
                UNION ALL
                SELECT time::date AS trade_day, open, 'fyers' as src
                FROM broker_fyers.ohlcv_1m
                WHERE symbol = $1
                  AND time::date BETWEEN $2 AND $3
                  AND time::time = $4::time
                  AND NOT EXISTS (
                      SELECT 1 FROM broker_upstox.ohlcv_1m u 
                      WHERE u.symbol = $1 AND u.time::date = broker_fyers.ohlcv_1m.time::date
                  )
            )
            SELECT trade_day, open, src
            FROM spot_data
            ORDER BY trade_day
        """
        async with pool.acquire() as connection:
            records = await connection.fetch(
                query,
                self.args.underlying_symbol,
                start_date,
                end_date,
                MARKET_OPEN_TIME,
            )
        
        results = []
        for r in records:
            results.append((r["trade_day"], float(r["open"])))
            if r["src"] == "fyers":
                logger.debug("Using Fyers spot fallback for date: %s", r["trade_day"])
                
        return results

    async def _process_trade_day(self, trade_day: date, spot_open: float, active_expiries: list[date]) -> int:
        atm_strike = round_to_strike(spot_open)
        logger.info(
            "Processing %s with spot %.2f, ATM %s, and %s active expiries",
            trade_day,
            spot_open,
            atm_strike,
            len(active_expiries),
        )

        contracts_by_expiry = await self._load_contracts_for_expiries(active_expiries)
        target_specs = build_target_contract_specs(atm_strike, self.args.atm_option_type)

        selected_contracts: list[dict[str, str]] = []
        for expiry in active_expiries:
            expiry_key = expiry.isoformat()
            contracts = contracts_by_expiry.get(expiry_key, [])
            if not contracts:
                logger.warning("No contracts returned for expiry %s on %s", expiry_key, trade_day)
                continue

            resolved_contracts = self._resolve_target_contracts(contracts, target_specs)
            if len(resolved_contracts) != TOTAL_SYMBOLS_PER_EXPIRY:
                logger.warning(
                    "Resolved %s/%s target contracts for expiry %s on %s",
                    len(resolved_contracts),
                    TOTAL_SYMBOLS_PER_EXPIRY,
                    expiry_key,
                    trade_day,
                )
            selected_contracts.extend(resolved_contracts)

        if not selected_contracts:
            logger.warning("No option contracts selected for %s", trade_day)
            return 0

        if self.args.dry_run:
            logger.info("Dry run: resolved %s symbols for %s", len(selected_contracts), trade_day)
            return 0

        # Smart Skipping Logic
        missing_contracts = await self._filter_existing_contracts(trade_day, selected_contracts)
        skipped = len(selected_contracts) - len(missing_contracts)
        if skipped > 0:
            logger.info("Smart Skip: %s contracts already in DB. Downloading %s missing.", skipped, len(missing_contracts))

        if not missing_contracts:
            return 0

        download_results = await self.fetcher.download_historical_candles_batch(
            [contract["instrument_key"] for contract in missing_contracts],
            trade_day.isoformat(),
            trade_day.isoformat(),
        )
        rows = self._build_upsert_rows(download_results, missing_contracts)
        if not rows:
            logger.warning("No candle rows returned for %s", trade_day)
            return 0

        await self._upsert_rows(rows)
        logger.info("Upserted %s rows for %s", len(rows), trade_day)
        return len(rows)

    async def _load_contracts_for_expiries(self, expiries: list[date]) -> dict[str, list[dict[str, object]]]:
        tasks = [
            self.fetcher.get_expired_option_contracts_batch(self.underlying_key, expiry.isoformat())
            for expiry in expiries
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        contracts_by_expiry: dict[str, list[dict[str, object]]] = {}
        for expiry, result in zip(expiries, results):
            expiry_key = expiry.isoformat()
            if isinstance(result, Exception):
                logger.warning("Failed to load contracts for expiry %s: %s", expiry_key, result)
                continue
            contracts_by_expiry[expiry_key] = [contract for contract in result if isinstance(contract, dict)]
        return contracts_by_expiry

    def _resolve_target_contracts(
        self,
        contracts: list[dict[str, object]],
        target_specs: list[tuple[int, str]],
    ) -> list[dict[str, str]]:
        contract_lookup: dict[tuple[int, str], dict[str, str]] = {}
        for contract in contracts:
            try:
                strike_price = int(round(float(contract["strike_price"])))
                instrument_type = str(contract["instrument_type"]).upper()
                instrument_key = str(contract["instrument_key"])
                trading_symbol = str(contract["trading_symbol"])
            except (KeyError, TypeError, ValueError):
                continue

            contract_lookup[(strike_price, instrument_type)] = {
                "instrument_key": instrument_key,
                "symbol": trading_symbol,
            }

        selected: list[dict[str, str]] = []
        for strike_price, instrument_type in target_specs:
            contract = contract_lookup.get((strike_price, instrument_type))
            if contract:
                selected.append(contract)
        return selected

    def _build_upsert_rows(
        self,
        download_results: list[dict[str, object]],
        contracts: list[dict[str, str]],
    ) -> list[tuple[datetime, str, float, float, float, float, int, int, float | None, float | None, str]]:
        symbol_lookup = {
            contract["instrument_key"]: contract["symbol"]
            for contract in contracts
        }
        rows: list[tuple[datetime, str, float, float, float, float, int, int, float | None, float | None, str]] = []

        for result in download_results:
            instrument_key = str(result.get("instrument_key", ""))
            symbol = symbol_lookup.get(instrument_key)
            if not symbol:
                continue

            candles = result.get("candles", [])
            if not isinstance(candles, list):
                continue

            for candle in candles:
                if len(candle) < 6:
                    continue
                
                # Upstox expired candles: [timestamp, open, high, low, close, volume, oi]
                # Index 6 is OI. Some older candles might only have 6 elements.
                oi = int(math.floor(float(candle[6]))) if len(candle) > 6 else 0

                rows.append(
                    (
                        extract_timestamp(candle[0]),
                        symbol,
                        float(candle[1]),
                        float(candle[2]),
                        float(candle[3]),
                        float(candle[4]),
                        int(math.floor(float(candle[5]))),
                        oi,
                        None,
                        None,
                        instrument_key,
                    )
                )
        
        if not rows and download_results:
            logger.debug("Parsing complete: 0 rows generated from %d download results", len(download_results))
            
        return rows

    async def _upsert_rows(self, rows: list[tuple[datetime, str, float, float, float, float, int, int, float | None, float | None, str]]) -> None:
        pool = await DatabaseManager.get_pool()
        query = """
            INSERT INTO broker_upstox.options_ohlc (
                time,
                symbol,
                open,
                high,
                low,
                close,
                volume,
                oi,
                calc_implied_volatility,
                calc_delta,
                instrument_key
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (time, symbol) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                oi = EXCLUDED.oi,
                calc_implied_volatility = EXCLUDED.calc_implied_volatility,
                calc_delta = EXCLUDED.calc_delta,
                instrument_key = EXCLUDED.instrument_key
        """
        async with pool.acquire() as connection:
            for batch in chunked(rows, UPSERT_BATCH_SIZE):
                await connection.executemany(query, batch)

    async def _filter_existing_contracts(self, trade_day: date, contracts: list[dict[str, str]]) -> list[dict[str, str]]:
        if not contracts:
            return []
            
        pool = await DatabaseManager.get_pool()
        symbols = [c["symbol"] for c in contracts]
        
        # Consider a contract "downloaded" if it has >300 candles for the day (handles normal sessions)
        query = """
            SELECT symbol
            FROM broker_upstox.options_ohlc
            WHERE time::date = $1 AND symbol = ANY($2)
            GROUP BY symbol
            HAVING COUNT(*) > 300
        """
        async with pool.acquire() as connection:
            records = await connection.fetch(query, trade_day, symbols)
            existing_symbols = {r["symbol"] for r in records}
            
        return [c for c in contracts if c["symbol"] not in existing_symbols]

    async def _inline_audit(self):
        pool = await DatabaseManager.get_pool()
        query = """
            SELECT * FROM (
                SELECT DISTINCT time::date as trade_date, symbol, instrument_key
                FROM broker_upstox.options_ohlc
                WHERE instrument_key IS NOT NULL
            ) sub
            ORDER BY random()
            LIMIT 3
        """
        async with pool.acquire() as connection:
            records = await connection.fetch(query)
            
        if not records:
            return
            
        logger.info("--- Performing Inline Audit on 3 Random Contracts ---")
        for r in records:
            trade_date = r["trade_date"]
            symbol = r["symbol"]
            instrument_key = r["instrument_key"]
            
            db_query = "SELECT COUNT(*) FROM broker_upstox.options_ohlc WHERE symbol = $1 AND time::date = $2"
            async with pool.acquire() as conn:
                db_count = await conn.fetchval(db_query, symbol, trade_date)
                
            results = await self.fetcher.download_historical_candles_batch([instrument_key], trade_date.isoformat(), trade_date.isoformat())
            api_count = len(results[0].get("candles", [])) if results and isinstance(results[0], dict) else 0
            
            if db_count == api_count:
                logger.info("✅ AUDIT MATCH: %s on %s has %s rows (DB) == %s rows (API)", symbol, trade_date, db_count, api_count)
            else:
                logger.error("❌ AUDIT MISMATCH: %s on %s has %s rows (DB) vs %s rows (API)", symbol, trade_date, db_count, api_count)
            await asyncio.sleep(1)


async def async_main() -> None:
    args = parse_args()
    configure_logging(args.verbose)
    syncer = UpstoxOptionsSync(args)
    await syncer.run()


if __name__ == "__main__":
    asyncio.run(async_main())