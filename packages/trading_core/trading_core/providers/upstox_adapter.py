import json
import os
from datetime import date, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from trading_core.providers.base import BrokerAdapter
from trading_core.auth import AuthManager

UPSTOX_API_BASE = "https://api.upstox.com"
CLIENT_ID = os.getenv("UPSTOX_CLIENT_ID", "")
SECRET_KEY = os.getenv("UPSTOX_SECRET_KEY", "")
REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "")

UPSTOX_UNDERLYING_KEYS = {
    "NSE:NIFTY50-INDEX": "NSE_INDEX|Nifty 50",
    "NSE:BANKNIFTY-INDEX": "NSE_INDEX|Nifty Bank",
    "NSE:NIFTYBANK-INDEX": "NSE_INDEX|Nifty Bank",
    "NSE:FINNIFTY-INDEX": "NSE_INDEX|Nifty Fin Service",
    "NSE:MIDCPNIFTY-INDEX": "NSE_INDEX|NIFTY MID SELECT",
}


class UpstoxAdapter(BrokerAdapter):
    def __init__(self):
        self._access_token = self._load_token()

    @property
    def provider_name(self) -> str:
        return "upstox"

    def _load_token(self) -> str:
        return AuthManager.load_token(self.provider_name)

    def _persist_token(self, token: str) -> None:
        AuthManager.save_token(self.provider_name, token)

    def _request(
        self,
        method: str,
        path: str,
        query: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        include_token: bool = True,
        form_encoded: bool = False,
    ):
        url = f"{UPSTOX_API_BASE}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"

        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 TradingEcosystem/1.0",
        }
        body = None
        if include_token:
            if not self._access_token:
                print("WARNING: Upstox access token not found. API calls may fail.")
            headers["Authorization"] = f"Bearer {self._access_token}"
        
        if data is not None:
            if form_encoded:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                body = urlencode(data).encode("utf-8")
            else:
                headers["Content-Type"] = "application/json"
                body = json.dumps(data).encode("utf-8")

        request = Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"Upstox API error: {error_body}") from exc
        except URLError as exc:
            raise ValueError(f"Upstox network error: {exc}") from exc

        return payload

    def validate_token(self) -> bool:
        # Hot-reload from disk to keep singletons in sync with CLI authentications
        self._access_token = self._load_token()
        if not self._access_token:
            return False
        try:
            response = self._request("GET", "/v2/user/profile")
        except ValueError:
            return False
        return bool(response.get("data", {}).get("is_active", False))

    def generate_auth_link(self) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "state": "upstox",
            }
        )
        return f"{UPSTOX_API_BASE}/v2/login/authorization/dialog?{query}"

    def fetch_access_token(self, auth_code: str) -> str:
        response = self._request(
            "POST",
            "/v2/login/authorization/token",
            data={
                "code": auth_code,
                "client_id": CLIENT_ID,
                "client_secret": SECRET_KEY,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            include_token=False,
            form_encoded=True,
        )
        access_token = response.get("access_token")
        if not access_token:
            raise ValueError(f"Failed to generate Upstox access token: {response}")
        self._access_token = access_token
        self._persist_token(access_token)
        return access_token

    def _aggregate_candles(self, candles: list[list], minutes: int) -> list[list]:
        if minutes <= 1 or not candles:
            return candles

        # Upstox returns newest-first in some endpoints. Normalize to oldest-first first.
        candles = sorted(candles, key=lambda row: int(row[0]))

        bucket_sec = minutes * 60
        aggregated: list[list] = []
        current_bucket = None
        current = None

        for row in candles:
            if len(row) < 6:
                continue
            ts = int(row[0])
            o = float(row[1])
            h = float(row[2])
            l = float(row[3])
            c = float(row[4])
            v = float(row[5])

            bucket = (ts // bucket_sec) * bucket_sec
            if current_bucket is None or bucket != current_bucket:
                if current is not None:
                    aggregated.append(current)
                current_bucket = bucket
                current = [bucket, o, h, l, c, v]
                continue

            current[2] = max(float(current[2]), h)
            current[3] = min(float(current[3]), l)
            current[4] = c
            current[5] = float(current[5]) + v

        if current is not None:
            aggregated.append(current)

        return aggregated

    def get_historical_data(self, symbol: str, start_date: str, end_date: str, resolution: str = "1"):
        from datetime import timedelta
        instrument_key = UPSTOX_UNDERLYING_KEYS.get(symbol, symbol)
        resolution_key = str(resolution).strip().lower()
        interval = "day"
        aggregate_minutes = 1

        if resolution_key in {"1", "1m"}:
            interval = "1minute"
            aggregate_minutes = 1
        elif resolution_key in {"5", "5m"}:
            # Upstox does not support 5minute directly; derive from 1minute.
            interval = "1minute"
            aggregate_minutes = 5
        elif resolution_key in {"10", "10m"}:
            interval = "1minute"
            aggregate_minutes = 10
        elif resolution_key in {"15", "15m"}:
            interval = "1minute"
            aggregate_minutes = 15
        elif resolution_key in {"30", "30m"}:
            interval = "30minute"
            aggregate_minutes = 1
        elif resolution_key in {"d", "1d", "day"}:
            interval = "day"
            aggregate_minutes = 1

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        normalized = []
        current_start = start_dt

        print(f"[*] Starting 30-day chunked download from {start_date} to {end_date}...")
        while current_start <= end_dt:
            current_end = min(current_start + timedelta(days=30), end_dt)
            
            # format required by Upstox history endpoint: YYYY-mm-dd
            from_date_str = current_start.strftime("%Y-%m-%d")
            to_date_str = current_end.strftime("%Y-%m-%d")
            
            print(f"  -> Fetching {from_date_str} to {to_date_str}...", end='\r', flush=True)

            if interval == "1minute" and from_date_str == to_date_str and from_date_str == date.today().isoformat():
                path = f"/v2/historical-candle/intraday/{quote(instrument_key, safe='')}/{interval}"
            else:
                path = f"/v2/historical-candle/{quote(instrument_key, safe='')}/{interval}/{to_date_str}/{from_date_str}"

            try:
                response = self._request("GET", path)
                candles = response.get("data", {}).get("candles", [])
                
                # Upstox returns newest first; standardizing for internally aligned downstream usage
                chunk_normalized = []
                for candle in candles:
                    ts = int(datetime.fromisoformat(candle[0]).timestamp())
                    chunk_normalized.append([ts, candle[1], candle[2], candle[3], candle[4], candle[5]])
                
                normalized.extend(chunk_normalized)
            except ValueError as e:
                print(f"\n[WARN] Upstox history error for {symbol} ({from_date_str} to {to_date_str}): {str(e)}")
                # Do not raise here so that we can skip gaps and fetch as much data as possible

            current_start = current_end + timedelta(days=1)

        print("\n[SUCCESS] Download stream complete.")
        normalized.sort(key=lambda x: x[0])
        return self._aggregate_candles(normalized, aggregate_minutes)

    def get_quotes(self, symbols: list[str]):
        if not symbols: return []
        response = self._request("GET", "/v2/market-quote/ohlc", query={"instrument_key": ",".join(symbols), "interval": "1d"})
        raw_data = response.get("data", {})
        quotes = []
        for sym in symbols:
            item = raw_data.get(sym)
            if item:
                quotes.append({"instrument_key": sym, "last_price": item.get("last_price")})
        return quotes

    def get_option_chain_symbols(self, underlying_symbol: str, expiry_date: str, strike_count: int = 10, as_of_date: str = None):
        underlying_key = UPSTOX_UNDERLYING_KEYS.get(underlying_symbol, underlying_symbol)
        
        if as_of_date:
            history = self.get_historical_data(underlying_key, as_of_date, as_of_date, "1")
            spot_price = history[0][4] if history else 0
        else:
            quotes = self.get_quotes([underlying_key])
            spot_price = quotes[0].get("last_price") if quotes else 0

        response = self._request("GET", "/v2/option/contract", query={"instrument_key": underlying_key})
        contracts = response.get("data", [])
        
        # Simple string-match expiry for now (to be standardizing later in the symbol core)
        matching = [c for c in contracts if expiry_date in c.get("expiry", "")]
        
        strikes = sorted({float(c.get("strike_price", 0)) for c in matching})
        if not strikes: return {"symbols": []}
        
        atm_strike = round(spot_price / 50) * 50 # Simplification
        idx = min(range(len(strikes)), key=lambda i: abs(strikes[i]-atm_strike))
        selected_strikes = strikes[max(0, idx-strike_count) : min(len(strikes), idx+strike_count+1)]
        
        final_contracts = [c for c in matching if float(c.get("strike_price")) in selected_strikes]
        
        return {
            "atm": atm_strike,
            "spot": spot_price,
            "symbols": [c["instrument_key"] for c in final_contracts],
            "contracts": final_contracts
        }

    def get_option_expiries(self, underlying_symbol: str) -> list[str]:
        underlying_key = UPSTOX_UNDERLYING_KEYS.get(underlying_symbol, underlying_symbol)
        response = self._request("GET", "/v2/option/contract", query={"instrument_key": underlying_key})
        contracts = response.get("data", [])

        expiries = sorted({str(contract.get("expiry")) for contract in contracts if contract.get("expiry")})
        return expiries

    def place_order(self, symbol: str, side: str, quantity: int, order_type: str = "MARKET", price: float = None, tag: str = ""):
        payload = {
            "quantity": int(quantity),
            "product": "I", # Intraday
            "validity": "DAY",
            "price": float(price) if price else 0.0,
            "tag": tag,
            "instrument_token": symbol,
            "order_type": order_type.upper(),
            "transaction_type": side.upper(),
            "disclosed_quantity": 0,
            "trigger_price": 0.0,
            "is_amo": False
        }
        response = self._request("POST", "/v2/order/place", data=payload)
        return response.get("data", {}).get("order_id")

    def get_positions(self):
        response = self._request("GET", "/v2/portfolio/net-positions")
        return response.get("data", [])

    def cancel_order(self, order_id: str):
        response = self._request("DELETE", "/v2/order/cancel", query={"order_id": order_id, "api-version": "2.0"})
        cancelled_id = response.get("data", {}).get("order_id")
        if not cancelled_id:
            raise ValueError(f"Upstox cancel_order response missing order_id: {response}")
        return cancelled_id

    def modify_order(self, order_id: str, quantity: int | None = None, price: float | None = None, order_type: str | None = None):
        payload: dict = {"order_id": order_id}
        if quantity is not None:
            payload["quantity"] = int(quantity)
        if price is not None:
            payload["price"] = float(price)
        if order_type is not None:
            payload["order_type"] = order_type.upper()
        response = self._request("PUT", "/v2/order/modify", data=payload)
        modified_id = response.get("data", {}).get("order_id")
        if not modified_id:
            raise ValueError(f"Upstox modify_order response missing order_id: {response}")
        return modified_id

    def get_trades(self):
        response = self._request("GET", "/v2/order/trades/get-trades-for-day")
        return response.get("data", [])
