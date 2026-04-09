class ProviderRegistry:
    def __init__(self):
        self._adapters = {}
        self._defaults_loaded = False

    def _ensure_defaults(self):
        if self._defaults_loaded:
            return

        from trading_core.providers.fyers_adapter import FyersAdapter
        from trading_core.providers.upstox_adapter import UpstoxAdapter

        self.register("fyers", FyersAdapter())
        self.register("upstox", UpstoxAdapter())
        self._defaults_loaded = True

    def register(self, name, adapter):
        self._adapters[name.lower()] = adapter

    def get_adapter(self, name):
        self._ensure_defaults()
        adapter = self._adapters.get(name.lower())
        if not adapter:
            raise ValueError(f"Provider '{name}' not found in registry.")
        return adapter

# Singleton instance
registry = ProviderRegistry()

def get_adapter(provider: str = "fyers"):
    return registry.get_adapter(provider)
