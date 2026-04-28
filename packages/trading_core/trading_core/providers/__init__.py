class ProviderRegistry:
    def __init__(self):
        self._adapters = {}

    def register(self, name, adapter):
        self._adapters[name.lower()] = adapter

    def _load_default(self, name):
        normalized = name.lower()
        if normalized in self._adapters:
            return
        if normalized == "fyers":
            from trading_core.providers.fyers_adapter import FyersAdapter

            self.register(normalized, FyersAdapter())
            return
        if normalized == "upstox":
            from trading_core.providers.upstox_adapter import UpstoxAdapter

            self.register(normalized, UpstoxAdapter())
            return
        if normalized == "zerodha":
            from trading_core.providers.zerodha_adapter import ZerodhaAdapter

            self.register(normalized, ZerodhaAdapter())
            return
        raise ValueError(f"Provider '{name}' not found in registry.")

    def get_adapter(self, name):
        self._load_default(name)
        return self._adapters[name.lower()]

# Singleton instance
registry = ProviderRegistry()

def get_adapter(provider: str = "fyers"):
    return registry.get_adapter(provider)
