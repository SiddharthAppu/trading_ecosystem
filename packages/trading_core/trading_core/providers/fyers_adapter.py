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
        # Hot-reload from disk to keep singletons in sync with CLI authentications
        self._access_token = self._load_token()
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
        from datetime import datetime, timedelta
        client = self._get_client()
        
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        all_candles = []
        current_start = start_dt
        
        print(f"[*] Starting 90-day chunked download from {start_date} to {end_date}...")
        while current_start <= end_dt:
            current_end = min(current_start + timedelta(days=90), end_dt)
            
            print(f"  -> Fetching {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}...", end='\r', flush=True)
            
            payload = {
                "symbol": symbol,
                "resolution": resolution,
                "date_format": "1",
                "range_from": current_start.strftime("%Y-%m-%d"),
                "range_to": current_end.strftime("%Y-%m-%d"),
                "cont_flag": "0"
            }
            response = client.history(payload)
            
            if response.get("s") == "ok":
                all_candles.extend(response.get("candles", []))
            else:
                err_msg = response.get("message", "Unknown Fyers error")
                print(f"\n[WARN] Fyers history error for {symbol} ({payload['range_from']} to {payload['range_to']}): {err_msg} (Status: {response.get('s')})")
                if not all_candles:
                    raise ValueError(f"Fyers history error: {err_msg}")
            
            current_start = current_end + timedelta(days=1)
            
        print("\n[SUCCESS] Download stream complete.")
        return all_candles

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

        # Convert YYYY-MM-DD to Fyers YY + MONTH_CODE + DD for weeklies natively recognized by the system
        if re.match(r'^\d{4}-\d{2}-\d{2}$', expiry_date):
            from datetime import datetime
            dt = datetime.strptime(expiry_date, "%Y-%m-%d")
            yy = dt.strftime("%y")
            dd = dt.strftime("%d")
            months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
            mon_str = months[dt.month - 1]
            m_code = MONTH_MAP[mon_str]
            final_expiry = f"{yy}{m_code}{dd}"
        else:
            final_expiry = expiry_date

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

    def _normalize_expiry(self, raw_expiry: str) -> str:
        value = str(raw_expiry).strip().upper()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            return value

        reverse_month_map = {v: k for k, v in MONTH_MAP.items()}
        if re.match(r"^\d{2}[1-9OND]\d{2}$", value):
            yy = int(value[:2])
            month_code = value[2]
            dd = value[3:]
            month_name = reverse_month_map.get(month_code)
            if not month_name:
                return value
            month_num = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"].index(month_name) + 1
            return f"20{yy:02d}-{month_num:02d}-{int(dd):02d}"

        return value

    def get_option_expiries(self, underlying_symbol: str) -> list[str]:
        client = self._get_client()
        payload_candidates = [
            {"symbol": underlying_symbol, "strikecount": 1},
            {"symbol": underlying_symbol, "strikecount": 1, "timestamp": ""},
        ]

        response = None
        for payload in payload_candidates:
            try:
                maybe_response = client.optionchain(payload)
            except Exception:
                continue
            if isinstance(maybe_response, dict) and maybe_response.get("s") == "ok":
                response = maybe_response
                break

        if not response:
            raise ValueError("Fyers option chain request failed. Unable to resolve expiries.")

        expiries = set()

        def collect_from_item(item):
            if not isinstance(item, dict):
                return
            for key in ("expiry", "expiryDate", "expiry_date", "date"):
                value = item.get(key)
                if value:
                    expiries.add(self._normalize_expiry(str(value)))

        data = response.get("data")
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, list):
                    for item in value:
                        collect_from_item(item)
                else:
                    collect_from_item(value)
        elif isinstance(data, list):
            for item in data:
                collect_from_item(item)

        if not expiries:
            raise ValueError("No expiries found in Fyers option chain response.")

        return sorted(expiries)
