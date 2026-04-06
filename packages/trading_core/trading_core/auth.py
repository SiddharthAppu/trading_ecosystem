import os
from typing import Optional, Dict
from trading_core.config import AUTH_DIR, get_auth_file

class AuthManager:
    """Centralized manager for broker authentication and token lifecycle."""
    
    TOKEN_FILES = {
        "fyers": ".access_token.txt",
        "upstox": ".upstox_access_token.txt"
    }

    @classmethod
    def get_token_path(cls, provider: str) -> str:
        filename = cls.TOKEN_FILES.get(provider.lower())
        if not filename:
            raise ValueError(f"Unknown provider: {provider}")
        return get_auth_file(filename)

    @classmethod
    def load_token(cls, provider: str) -> str:
        """Loads a token from file or environment."""
        provider = provider.lower()
        
        # Priority 1: Environment Variable
        env_key = f"{provider.upper()}_ACCESS_TOKEN"
        token = os.getenv(env_key)
        if token:
            return token
            
        # Priority 2: Token File
        path = cls.get_token_path(provider)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        
        return ""

    @classmethod
    def save_token(cls, provider: str, token: str) -> None:
        """Persists a token to the central auth directory."""
        path = cls.get_token_path(provider)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(token)

    @classmethod
    def is_authenticated(cls, provider: str) -> bool:
        """Checks if a valid session exists for the provider."""
        from trading_core.providers import get_adapter
        adapter = get_adapter(provider)
        return adapter.validate_token()

    @classmethod
    def get_authenticated_adapter(cls, provider: str):
        """Returns an adapter instance, ensuring it has the latest token loaded."""
        from trading_core.providers import get_adapter
        adapter = get_adapter(provider)
        # Note: Adapters already load tokens in their __init__ via load_token logic,
        # but we can force refresh if needed here in the future.
        return adapter

auth_manager = AuthManager()
