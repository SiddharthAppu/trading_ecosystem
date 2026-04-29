import csv
import hashlib
import io
import os
from datetime import date, datetime, timedelta

import requests

from trading_core.auth import AuthManager
from trading_core.providers.base import BrokerAdapter


API_KEY = os.getenv("ZERODHA_API_KEY", "")
API_SECRET = os.getenv("ZERODHA_API_SECRET", "")
REDIRECT_URI = os.getenv("ZERODHA_REDIRECT_URI", "")

ZERODHA_BASE_URL = "https://api.kite.trade"
ZERODHA_LOGIN_URL = "https://kite.trade/connect/login"

UNDERLYING_ALIASES = {
    "NSE:NIFTY50-INDEX": "NIFTY 50",
    "NSE:NIFTY50": "NIFTY 50",
    "NSE:NIFTY BANK": "NIFTY BANK",
    "NSE:BANKNIFTY-INDEX": "NIFTY BANK",
    "NSE:NIFTYBANK-INDEX": "NIFTY BANK",
    "NSE:FINNIFTY-INDEX": "NIFTY FIN SERVICE",
    "NSE:MIDCPNIFTY-INDEX": "NIFTY MID SELECT",
}


class ZerodhaAdapter(BrokerAdapter):
    def __init__(self):
        self._access_token = self._load_token()
        self.base_url = ZERODHA_BASE_URL
        self._instrument_cache: list[dict] = []
        self._instrument_cache_date: date | None = None

    @property
    def provider_name(self) -> str:
        return "zerodha"

    def _load_token(self) -> str:
        return AuthManager.load_token(self.provider_name)

    def _persist_token(self, token: str) -> None:
        AuthManager.save_token(self.provider_name, token)

    def _headers(self, include_token: bool = True) -> dict[str, str]:
        headers = {
            "X-Kite-Version": "3",
            "Accept": "application/json",
            "User-Agent": "TradingEcosystem/1.0",
        }
        if include_token:
            if not self._access_token:
                self._access_token = self._load_token()
            if not self._access_token:
                raise ValueError("Zerodha access token not found. Authenticate first.")
            headers["Authorization"] = f"token {API_KEY}:{self._access_token}"
        return headers

    def _request_json(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        data: dict | None = None,
        include_token: bool = True,
        timeout: int = 30,
    ) -> dict:
        url = f"{self.base_url}{path}"
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=self._headers(include_token=include_token),
            params=params,
            data=data,
            timeout=timeout,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError(f"Zerodha API returned non-JSON response for {path}") from exc

        if response.status_code >= 400:
            raise ValueError(f"Zerodha API error ({response.status_code}): {payload}")
        if payload.get("status") == "error":
            raise ValueError(f"Zerodha API error: {payload}")
        return payload

    def _request_text(self, path: str, timeout: int = 60) -> str:
        url = f"{self.base_url}{path}"
        response = requests.get(url, headers=self._headers(include_token=True), timeout=timeout)
        if response.status_code >= 400:
            raise ValueError(f"Zerodha API error ({response.status_code}) for {path}: {response.text[:500]}")
        return response.text

    def _normalize_symbol(self, symbol: str) -> str:
        return UNDERLYING_ALIASES.get(symbol, symbol)

    def _ensure_instruments(self) -> list[dict]:
        today = date.today()
        if self._instrument_cache and self._instrument_cache_date == today:
            return self._instrument_cache

        raw_csv = self._request_text("/instruments")
        reader = csv.DictReader(io.StringIO(raw_csv))
        self._instrument_cache = list(reader)
        self._instrument_cache_date = today
        return self._instrument_cache

    def _resolve_instrument(self, symbol: str) -> dict:
        normalized = self._normalize_symbol(symbol)
        if ":" in normalized:
            exchange, tradingsymbol = normalized.split(":", 1)
            if exchange.upper() == "NSE_INDEX":
                exchange = "NSE"
        else:
            exchange, tradingsymbol = "NSE", normalized

        instruments = self._ensure_instruments()
        for row in instruments:
            if row.get("exchange") == exchange and row.get("tradingsymbol") == tradingsymbol:
                return row

        # Fallback for index names present as `name` (e.g. NIFTY 50)
        for row in instruments:
            if row.get("exchange") == exchange and row.get("name") == tradingsymbol:
                return row

        raise ValueError(f"Zerodha instrument not found for symbol: {symbol}")

    def _interval(self, resolution: str) -> str:
        value = str(resolution).strip().lower()
        mapping = {
            "1": "minute",
            "1m": "minute",
            "3": "3minute",
            "3m": "3minute",
            "5": "5minute",
            "5m": "5minute",
            "10": "10minute",
            "10m": "10minute",
            "15": "15minute",
            "15m": "15minute",
            "30": "30minute",
            "30m": "30minute",
            "60": "60minute",
            "60m": "60minute",
            "d": "day",
            "1d": "day",
            "day": "day",
        }
        return mapping.get(value, "minute")

    def _to_timestamp(self, candle_time: str) -> int:
        return int(datetime.fromisoformat(candle_time).timestamp())

    def _fetch_ltp(self, symbol: str) -> float:
        normalized = self._normalize_symbol(symbol)
        payload = self._request_json("GET", "/quote/ltp", params={"i": [normalized]})
        data = payload.get("data", {})
        item = data.get(normalized)
        if not item:
            return 0.0
        return float(item.get("last_price") or 0.0)

    def validate_token(self) -> bool:
        self._access_token = self._load_token()
        if not self._access_token:
            return False
        try:
            payload = self._request_json("GET", "/user/profile")
        except ValueError:
            return False
        return bool(payload.get("data"))

    def generate_auth_link(self) -> str:
        if not API_KEY:
            raise ValueError("ZERODHA_API_KEY is not configured.")
        return f"{ZERODHA_LOGIN_URL}?api_key={API_KEY}&v=3"

    def fetch_access_token(self, auth_code: str) -> str:
        if not API_KEY or not API_SECRET:
            raise ValueError("ZERODHA_API_KEY / ZERODHA_API_SECRET not configured.")

        checksum = hashlib.sha256((API_KEY + auth_code + API_SECRET).encode("utf-8")).hexdigest()
        payload = self._request_json(
            "POST",
            "/session/token",
            data={
                "api_key": API_KEY,
                "request_token": auth_code,
                "checksum": checksum,
            },
            include_token=False,
        )

        access_token = payload.get("data", {}).get("access_token")
        if not access_token:
            raise ValueError(f"Failed to generate Zerodha access token: {payload}")

        self._access_token = access_token
        self._persist_token(access_token)
        return access_token

    def get_historical_data(self, symbol: str, start_date: str, end_date: str, resolution: str = "1"):
        instrument = self._resolve_instrument(symbol)
        token = instrument.get("instrument_token")
        if not token:
            raise ValueError(f"Instrument token not found for symbol: {symbol}")

        interval = self._interval(resolution)
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        candles: list[list] = []
        chunk_days = 60 if interval != "day" else 365
        current_start = start_dt

        while current_start <= end_dt:
            current_end = min(current_start + timedelta(days=chunk_days), end_dt)
            payload = self._request_json(
                "GET",
                f"/instruments/historical/{token}/{interval}",
                params={
                    "from": current_start.strftime("%Y-%m-%d"),
                    "to": current_end.strftime("%Y-%m-%d"),
                    "oi": 1,
                },
            )

            rows = payload.get("data", {}).get("candles", [])
            for row in rows:
                if len(row) < 6:
                    continue
                candles.append([
                    self._to_timestamp(row[0]),
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                ])

            current_start = current_end + timedelta(days=1)

        candles.sort(key=lambda x: x[0])
        return candles

    def get_quotes(self, symbols: list[str]):
        if not symbols:
            return []
        normalized = [self._normalize_symbol(symbol) for symbol in symbols]
        payload = self._request_json("GET", "/quote", params={"i": normalized})
        raw = payload.get("data", {})

        quotes = []
        for symbol in normalized:
            item = raw.get(symbol, {})
            ohlc = item.get("ohlc", {})
            quotes.append(
                {
                    "instrument_key": symbol,
                    "last_price": item.get("last_price"),
                    "open": ohlc.get("open"),
                    "high": ohlc.get("high"),
                    "low": ohlc.get("low"),
                    "close": ohlc.get("close"),
                }
            )
        return quotes

    def get_option_chain_symbols(
        self,
        underlying_symbol: str,
        expiry_date: str,
        strike_count: int = 10,
        as_of_date: str | None = None,
    ) -> dict:
        instruments = self._ensure_instruments()
        normalized_underlying = self._normalize_symbol(underlying_symbol)
        name_key = normalized_underlying.split(":", 1)[-1]

        option_rows = [
            row
            for row in instruments
            if row.get("segment") == "NFO-OPT" and row.get("name") == name_key
        ]

        if not option_rows:
            return {"atm": 0.0, "spot": 0.0, "symbols": [], "contracts": []}

        target_expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        option_rows = [
            row for row in option_rows if row.get("expiry") and datetime.strptime(row["expiry"], "%Y-%m-%d").date() == target_expiry
        ]

        if not option_rows:
            return {"atm": 0.0, "spot": 0.0, "symbols": [], "contracts": []}

        if as_of_date:
            day_rows = self.get_historical_data(underlying_symbol, as_of_date, as_of_date, "1")
            spot = float(day_rows[-1][4]) if day_rows else 0.0
        else:
            spot = self._fetch_ltp(underlying_symbol)

        strikes = sorted({float(row.get("strike") or 0) for row in option_rows if row.get("strike")})
        if not strikes:
            return {"atm": 0.0, "spot": spot, "symbols": [], "contracts": []}

        atm = min(strikes, key=lambda strike: abs(strike - spot))
        atm_index = strikes.index(atm)
        selected_strikes = set(strikes[max(0, atm_index - strike_count) : atm_index + strike_count + 1])

        selected = [row for row in option_rows if float(row.get("strike") or 0) in selected_strikes]
        selected.sort(key=lambda row: (float(row.get("strike") or 0), row.get("instrument_type") or ""))

        contracts = [
            {
                "instrument_key": f"NFO:{row['tradingsymbol']}",
                "instrument_token": row.get("instrument_token"),
                "strike_price": float(row.get("strike") or 0),
                "instrument_type": row.get("instrument_type"),
                "expiry": row.get("expiry"),
            }
            for row in selected
        ]

        return {
            "atm": atm,
            "spot": spot,
            "symbols": [contract["instrument_key"] for contract in contracts],
            "contracts": contracts,
        }

    def get_option_expiries(self, underlying_symbol: str) -> list[str]:
        instruments = self._ensure_instruments()
        normalized_underlying = self._normalize_symbol(underlying_symbol)
        name_key = normalized_underlying.split(":", 1)[-1]

        expiries = {
            row.get("expiry")
            for row in instruments
            if row.get("segment") == "NFO-OPT" and row.get("name") == name_key and row.get("expiry")
        }
        return sorted(expiry for expiry in expiries if expiry)

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str = "MARKET",
        price: float | None = None,
        tag: str = "",
    ):
        normalized = self._normalize_symbol(symbol)
        if ":" in normalized:
            exchange, tradingsymbol = normalized.split(":", 1)
        else:
            exchange, tradingsymbol = "NSE", normalized

        payload = {
            "exchange": exchange,
            "tradingsymbol": tradingsymbol,
            "transaction_type": side.upper(),
            "quantity": int(quantity),
            "order_type": order_type.upper(),
            "product": "MIS",
            "validity": "DAY",
            "variety": "regular",
            "tag": (tag[:20] if tag else "ASTRA"),
        }
        if price is not None and order_type.upper() != "MARKET":
            payload["price"] = float(price)

        response = self._request_json("POST", "/orders/regular", data=payload)
        order_id = response.get("data", {}).get("order_id")
        if not order_id:
            raise ValueError(f"Zerodha order response missing order_id: {response}")
        return order_id

    def get_positions(self):
        response = self._request_json("GET", "/portfolio/positions")
        return response.get("data", {}).get("net", [])

    def get_order_status(self, order_id: str):
        orders = self.get_orders()
        for order in reversed(orders):
            if str(order.get("order_id")) == str(order_id):
                return order
        return None

    def get_orders(self):
        response = self._request_json("GET", "/orders")
        return response.get("data", [])

    def get_available_funds(self):
        margins = self.get_margin()
        equity = margins.get("equity", {})
        return {
            "available": equity.get("available", {}),
            "utilised": equity.get("utilised", {}),
            "net": equity.get("net"),
        }

    def get_margin(self):
        response = self._request_json("GET", "/user/margins")
        return response.get("data", {})

    def get_portfolio_status(self):
        return {
            "positions": self.get_positions(),
            "orders": self.get_orders(),
            "funds": self.get_available_funds(),
            "margin": self.get_margin(),
        }

    def cancel_order(self, order_id: str):
        response = self._request_json(
            "DELETE",
            f"/orders/regular/{order_id}",
            data={"variety": "regular", "order_id": order_id},
        )
        cancelled_id = response.get("data", {}).get("order_id")
        if not cancelled_id:
            raise ValueError(f"Zerodha cancel_order response missing order_id: {response}")
        return cancelled_id

    def modify_order(self, order_id: str, quantity: int | None = None, price: float | None = None, order_type: str | None = None):
        data: dict = {"variety": "regular", "order_id": order_id}
        if quantity is not None:
            data["quantity"] = int(quantity)
        if price is not None:
            data["price"] = float(price)
        if order_type is not None:
            data["order_type"] = order_type.upper()
        response = self._request_json("PUT", f"/orders/regular/{order_id}", data=data)
        modified_id = response.get("data", {}).get("order_id")
        if not modified_id:
            raise ValueError(f"Zerodha modify_order response missing order_id: {response}")
        return modified_id

    def get_trades(self):
        response = self._request_json("GET", "/trades")
        return response.get("data", [])
