"""Trading Core Shared Package."""

__all__ = ["AuthManager", "DatabaseManager", "DB_URL", "get_adapter"]


def __getattr__(name: str):
	if name == "AuthManager":
		from trading_core.auth import auth_manager as auth_manager

		return auth_manager
	if name == "get_adapter":
		from trading_core.providers import get_adapter as provider_get_adapter

		return provider_get_adapter
	if name == "DatabaseManager":
		from trading_core.db import DatabaseManager as db_manager

		return db_manager
	if name == "DB_URL":
		from trading_core.config import DB_URL as db_url

		return db_url
	raise AttributeError(f"module 'trading_core' has no attribute {name!r}")
