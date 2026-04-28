from abc import ABC, abstractmethod


class BrokerAdapter(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the internal provider name (e.g., 'fyers', 'upstox')."""
        raise NotImplementedError()

    @abstractmethod
    def validate_token(self) -> bool:
        """Checks if the currently stored access token is valid."""
        raise NotImplementedError()

    @abstractmethod
    def generate_auth_link(self) -> str:
        """Returns the OAuth login URL for the broker."""
        raise NotImplementedError()

    @abstractmethod
    def fetch_access_token(self, auth_code: str) -> str:
        """Exchanges an auth code for an access token and persists it."""
        raise NotImplementedError()

    @abstractmethod
    def get_historical_data(self, symbol: str, start_date: str, end_date: str, resolution: str = "1"):
        """Fetches historical OHLCV data."""
        raise NotImplementedError()

    @abstractmethod
    def get_quotes(self, symbols: list[str]):
        """Fetches current market quotes for one or more symbols."""
        raise NotImplementedError()

    @abstractmethod
    def get_option_chain_symbols(
        self, underlying_symbol: str, expiry_date: str, strike_count: int = 10, as_of_date: str = None
    ) -> dict:
        """Generates a list of option chain symbols around the ATM strike."""
        raise NotImplementedError()

    @abstractmethod
    def get_option_expiries(self, underlying_symbol: str) -> list[str]:
        """Returns available option expiries for the given underlying symbol."""
        raise NotImplementedError()

    @abstractmethod
    def place_order(self, symbol: str, side: str, quantity: int, order_type: str = "MARKET", price: float = None, tag: str = ""):
        """Places an order with the broker."""
        raise NotImplementedError()

    @abstractmethod
    def get_positions(self):
        """Fetches current open positions from the broker."""
        raise NotImplementedError()
