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

    def get_order_status(self, order_id: str):
        """Fetches status/details for a specific broker order id."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement get_order_status")

    def get_orders(self):
        """Fetches broker order book for the current session/account."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement get_orders")

    def get_available_funds(self):
        """Fetches currently available funds/cash for trading."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement get_available_funds")

    def get_margin(self):
        """Fetches margin details for the account."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement get_margin")

    def get_portfolio_status(self):
        """Fetches a normalized account snapshot (positions/holdings/funds where supported)."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement get_portfolio_status")

    def cancel_order(self, order_id: str):
        """Cancels a pending order by broker order id. Returns the cancelled order_id on success."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement cancel_order")

    def modify_order(self, order_id: str, quantity: int | None = None, price: float | None = None, order_type: str | None = None):
        """Modifies a pending order. Only supplied fields are updated. Returns the modified order_id."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement modify_order")

    def get_trades(self):
        """Fetches executed trade fills (tradebook) for the current session."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement get_trades")
