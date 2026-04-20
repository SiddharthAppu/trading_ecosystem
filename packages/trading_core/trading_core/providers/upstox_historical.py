import asyncio
import urllib.parse

import aiohttp

from trading_core.providers.upstox_adapter import UPSTOX_API_BASE, UpstoxAdapter

import os
import logging

log_file_path = "logs/upstox_historical_downloads.log"
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

audit_logger = logging.getLogger("upstox_audit_logger")
audit_logger.setLevel(logging.INFO)
if not audit_logger.handlers:
    fh = logging.FileHandler(log_file_path)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    audit_logger.addHandler(fh)

class UpstoxHistoricalDataFetcher:
    def __init__(self):
        self.adapter = UpstoxAdapter()
        if not self.adapter._access_token:
            self.adapter.validate_token()
        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.adapter._access_token}"
        }

    async def _get_json(self, path: str, params: dict[str, str] | None = None):
        url = f"{UPSTOX_API_BASE}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise ValueError(f"Failed request for {url}: {await response.text()}")
                return await response.json()

    async def get_expired_expiries(self, instrument_key: str):
        """Fetch all available expired expiry dates for an underlying instrument."""
        payload = await self._get_json(
            "/v2/expired-instruments/expiries",
            {"instrument_key": instrument_key},
        )
        return payload.get("data", [])

    async def get_expired_option_contracts_batch(self, instrument_key: str, expiry_date: str):
        """Fetch all expired option contracts for an underlying instrument and expiry date."""
        payload = await self._get_json(
            "/v2/expired-instruments/option/contract",
            {"instrument_key": instrument_key, "expiry_date": expiry_date},
        )
        return payload.get("data", [])

    async def _fetch_candle(self, session, instrument_key, from_date, to_date):
        import json
        url = f"{UPSTOX_API_BASE}/v2/expired-instruments/historical-candle/{urllib.parse.quote(instrument_key, safe='')}/1minute/{to_date}/{from_date}"
        
        expected_rows = 375
        max_retries = 5
        
        for attempt in range(max_retries):
            async with session.get(url) as response:
                status = response.status
                text = await response.text()
                
            audit_logger.info(f"Target: {instrument_key} | Date: {from_date} | Attempt: {attempt+1}/{max_retries} | HTTP: {status}")

            # The 1.0s Sleep: Slowing down massively to guarantee accuracy.
            await asyncio.sleep(1.0)

            if status == 429:
                if attempt < max_retries - 1:
                    print(f"[WARN] 429 Rate Limit for {instrument_key}. Waiting 10s...")
                    await asyncio.sleep(10)
                    continue
                print(f"[ERROR] Rate limit exhausted for {instrument_key} after {max_retries} retries")
                audit_logger.error(f"FAILURE: Rate limit exhausted for {instrument_key}")
                return {"error": "rate_limit", "instrument_key": instrument_key}
            
            if status != 200:
                print(f"[WARN] Failed to fetch {instrument_key} (status {status}): {text}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(10)
                    continue
                audit_logger.error(f"FAILURE: HTTP {status} for {instrument_key} - {text}")
                return {"instrument_key": instrument_key, "candles": []}
            
            try:
                data = json.loads(text)
            except Exception:
                data = {}
                
            api_status = data.get("status", "")
            candles = data.get("data", {}).get("candles", [])
            
            if not candles:
                if api_status == "success":
                    audit_logger.info(f"SUCCESS: Legitimate zero-volume day for {instrument_key}. Terminating retries.")
                    print(f"[INFO] 0-volume market day for {instrument_key}. Skipping retries.")
                    return {"instrument_key": instrument_key, "candles": []}
                
                # If there are no candles and status is NOT success
                if attempt < max_retries - 1:
                    print(f"\n[DEBUG] Empty payload for {instrument_key}. Raw text from Upstox: {text}")
                    print(f"[INFO] Empty candles for {instrument_key}, wait 10s to retry... (Attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(10)
                    continue
                
            # The Integrity Logger
            match_status = "OK" if len(candles) == expected_rows else "MISMATCH"
            audit_logger.info(f"SUCCESS: Fetched {len(candles)} rows for {instrument_key}. Match: {match_status}")
            
            # Attempt to make instrument_key pretty if possible, else use raw
            pretty_name = instrument_key.split(":")[-1] if ":" in instrument_key else instrument_key
            print(f"Fetched {len(candles)} rows for {pretty_name}. Expected {expected_rows}. Match: {match_status}.")
                
            return {"instrument_key": instrument_key, "candles": candles}
        
        audit_logger.warning(f"FAILURE: Retries exhausted for {instrument_key}")
        return {"instrument_key": instrument_key, "candles": []}

    async def download_historical_candles_batch(self, instrument_keys: list[str], from_date: str, to_date: str):
        """Rate limited batch downloader."""
        # Forced serialization (max concurrency = 1) for extreme safety
        semaphore = asyncio.Semaphore(1)

        async def bounded_fetch(session, key):
            async with semaphore:
                return await self._fetch_candle(session, key, from_date, to_date)

        results = []
        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = [asyncio.create_task(bounded_fetch(session, key)) for key in instrument_keys]
            results = await asyncio.gather(*tasks)

        return results

