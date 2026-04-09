import asyncio
import urllib.parse

import aiohttp

from trading_core.providers.upstox_adapter import UPSTOX_API_BASE, UpstoxAdapter

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
        url = f"{UPSTOX_API_BASE}/v2/expired-instruments/historical-candle/{urllib.parse.quote(instrument_key, safe='')}/1minute/{to_date}/{from_date}"
        async with session.get(url) as response:
            if response.status == 429:
                return {"error": "rate_limit", "instrument_key": instrument_key}
            if response.status != 200:
                print(f"[WARN] Failed to fetch {instrument_key}: {await response.text()}")
                return {"instrument_key": instrument_key, "candles": []}
            data = await response.json()
            return {"instrument_key": instrument_key, "candles": data.get("data", {}).get("candles", [])}

    async def download_historical_candles_batch(self, instrument_keys: list[str], from_date: str, to_date: str):
        """Rate limited batch downloader. Allows 50 req/sec maximum."""
        semaphore = asyncio.Semaphore(40)

        async def bounded_fetch(session, key):
            async with semaphore:
                await asyncio.sleep(0.02)
                return await self._fetch_candle(session, key, from_date, to_date)

        results = []
        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = [bounded_fetch(session, key) for key in instrument_keys]
            results = await asyncio.gather(*tasks)

        return results
