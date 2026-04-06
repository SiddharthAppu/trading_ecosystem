import os
import re
from fyers_apiv3 import fyersModel
from trading_core.providers.base import BrokerAdapter
from trading_core.auth import AuthManager

# Standardized credentials from config
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")

MONTH_MAP = {
    "JAN": "1", "FEB": "2", "MAR": "3", "APR": "4", "MAY": "5", "JUN": "6",
    "JUL": "7", "AUG": "8", "SEP": "9", "OCT": "O", "NOV": "N", "DEC": "D"
}


class FyersAdapter(BrokerAdapter):
    def __init__(self):
        self._access_token = self._load_token()

    @property
    def provider_name(self) -> str:
        return "fyers"

    def _load_token(self) -> str:
        return AuthManager.load_token(self.provider_name)

    def _persist_token(self, token: str) -> None:
        AuthManager.save_token(self.provider_name, token)

    def _get_client(self):
        if not self._access_token:
            print(f"WARNING: FYERS access token not set at {TOKEN_FILE}. API calls may fail.")
        return fyersModel.FyersModel(
            client_id=CLIENT_ID,
            is_async=False,
            token=self._access_token,
            log_path=""
        )

    def validate_token(self) -> bool:
        if not self._access_token:
            return False
        try:
            client = self._get_client()
            response = client.get_profile()
            return response.get("s") == "ok"
        except Exception:
            return False

    def generate_auth_link(self) -> str:
        session = fyersModel.SessionModel(
            client_id=CLIENT_ID,
            secret_key=SECRET_KEY,
            redirect_uri=REDIRECT_URI,
            response_type="code",
            state="fyers",
            grant_type="authorization_code"
        )
        return session.generate_authcode()

    def fetch_access_token(self, auth_code: str) -> str:
        session = fyersModel.SessionModel(
            client_id=CLIENT_ID,
            secret_key=SECRET_KEY,
            redirect_uri=REDIRECT_URI,
            response_type="code",
            grant_type="authorization_code"
        )
        session.set_token(auth_code)
        response = session.generate_token()

        if response.get("s") != "ok":
            raise ValueError(f"Failed to generate Fyers access token: {response}")

        self._access_token = response.get("access_token")
        self._persist_token(self._access_token)
        return self._access_token

    def get_historical_data(self, symbol: str, start_date: str, end_date: str, resolution: str = "1"):
        client = self._get_client()
        payload = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": "1",
            "range_from": start_date,
            "range_to": end_date,
            "cont_flag": "0"
        }
        response = client.history(payload)
        if response.get("s") == "ok":
            return response.get("candles", [])
        
        err_msg = response.get("message", "Unknown Fyers error")
        raise ValueError(f"Fyers history error for {symbol}: {err_msg} (Status: {response.get('s')})")

    def get_quotes(self, symbols: list[str]):
        client = self._get_client()
        payload = {"symbols": ",".join(symbols)}
        response = client.quotes(payload)
        if response.get("s") == "ok":
            return response.get("d", [])
        print(f"Error fetching Fyers quotes: {response}")
        return []

    def get_option_chain_symbols(self, underlying_symbol: str, expiry_date: str, strike_count: int = 10, as_of_date: str = None):
        if as_of_date:
            history = self.get_historical_data(underlying_symbol, as_of_date, as_of_date, "1")
            if not history:
                raise ValueError(f"No historical spot data for {underlying_symbol} on {as_of_date}")
            spot_price = history[0][4] # close price
        else:
            quotes = self.get_quotes([underlying_symbol])
            if not quotes:
                raise ValueError(f"Could not fetch spot price for {underlying_symbol}")
            spot_price = quotes[0].get("v", {}).get("lp")

        strike_gap = 100 if "BANKNIFTY" in underlying_symbol else 50
        atm_strike = round(spot_price / strike_gap) * strike_gap

        base_symbol = underlying_symbol.split(":")[1].split("-")[0]
        if "NIFTY50" in underlying_symbol:
            base_symbol = "NIFTY"

        # Simple conversion for Fyers expiry format (YYMMDD)
        # e.g., 20MAR as expected
        final_expiry = expiry_date
        # (This remains as is from the original adapter for now)

        symbols = []
        for offset in range(-strike_count, strike_count + 1):
            strike = int(atm_strike + (offset * strike_gap))
            for option_type in ["CE", "PE"]:
                symbols.append(f"NSE:{base_symbol}{final_expiry}{strike}{option_type}")

        contracts = []
        for sym in symbols:
            match = re.search(r'(\d+)(CE|PE)$', sym)
            strike = int(match.group(1)) if match else 0
            opt_type = match.group(2) if match else "XX"
            contracts.append({
                "instrument_key": sym,
                "strike_price": strike,
                "instrument_type": opt_type
            })

        return {
            "atm": atm_strike,
            "spot": spot_price,
            "symbols": symbols,
            "contracts": contracts,
        }
