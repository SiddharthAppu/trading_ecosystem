import os
import requests
from trading_core.providers.base import BrokerAdapter
from trading_core.auth import AuthManager

# Standardized credentials from config
API_KEY = os.getenv("ZERODHA_API_KEY")
API_SECRET = os.getenv("ZERODHA_API_SECRET")
REDIRECT_URI = os.getenv("ZERODHA_REDIRECT_URI")

class ZerodhaAdapter(BrokerAdapter):
    def __init__(self):
        self._access_token = self._load_token()
        self.base_url = "https://api.kite.trade"

    @property
    def provider_name(self) -> str:
        return "zerodha"

    def _load_token(self) -> str:
        return AuthManager.load_token(self.provider_name)

    def _persist_token(self, token: str) -> None:
        AuthManager.save_token(self.provider_name, token)

    def validate_token(self) -> bool:
        self._access_token = self._load_token()
        if not self._access_token:
            return False
        
        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {API_KEY}:{self._access_token}"
        }
        try:
            response = requests.get(f"{self.base_url}/user/profile", headers=headers, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def generate_auth_link(self) -> str:
        return f"https://kite.trade/connect/login?api_key={API_KEY}&v=3"

    def fetch_access_token(self, auth_code: str) -> str:
        import hashlib
        checksum = hashlib.sha256((API_KEY + auth_code + API_SECRET).encode("utf-8")).hexdigest()
        
        payload = {
            "api_key": API_KEY,
            "request_token": auth_code,
            "checksum": checksum
        }
        
        response = requests.post(f"{self.base_url}/session/token", data=payload)
        data = response.json()
        
        if response.status_code != 200:
            raise ValueError(f"Failed to generate Zerodha access token: {data}")

        self._access_token = data.get("data", {}).get("access_token")
        self._persist_token(self._access_token)
        return self._access_token

    def get_historical_data(self, symbol: str, start_date: str, end_date: str, resolution: str = "minute"):
        # Zerodha instrument tokens are needed here. This is a placeholder as 
        # mapping symbols to tokens usually requires a local CSV sync.
        raise NotImplementedError("Zerodha historical data requires instrument token mapping.")

    def get_quotes(self, symbols: list[str]):
        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {API_KEY}:{self._access_token}"
        }
        params = {"i": symbols}
        response = requests.get(f"{self.base_url}/quote", headers=headers, params=params)
        return response.json().get("data", {})

    def get_option_chain_symbols(self, underlying_symbol: str, expiry_date: str, strike_count: int = 10, as_of_date: str = None):
        raise NotImplementedError("Zerodha option chain requires instrument token mapping.")

    def get_option_expiries(self, underlying_symbol: str) -> list[str]:
        raise NotImplementedError("Zerodha option expiries requires instrument token mapping.")

    def place_order(self, symbol: str, side: str, quantity: int, order_type: str = "MARKET", price: float = None, tag: str = ""):
        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {API_KEY}:{self._access_token}"
        }
        
        # Zerodha usually needs 'NSE:NIFTY50' format but the 'exchange' and 'tradingsymbol' split.
        # This is a simplified mapper.
        if ":" in symbol:
            exchange, tradingsymbol = symbol.split(":")
        else:
            exchange, tradingsymbol = "NSE", symbol

        payload = {
            "exchange": exchange,
            "tradingsymbol": tradingsymbol,
            "transaction_type": side.upper(),
            "quantity": quantity,
            "order_type": order_type.upper(),
            "product": "MIS", # Default to intraday
            "validity": "DAY",
            "tag": tag[:8] if tag else "ASTRA"
        }
        
        if price:
            payload["price"] = price

        response = requests.post(f"{self.base_url}/orders/regular", headers=headers, data=payload)
        data = response.json()
        
        if response.status_code != 200:
            raise ValueError(f"Zerodha Order Failed: {data.get('message')}")
            
        return data.get("data", {}).get("order_id")

    def get_positions(self):
        headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {API_KEY}:{self._access_token}"
        }
        response = requests.get(f"{self.base_url}/portfolio/positions", headers=headers)
        return response.json().get("data", {}).get("net", [])
