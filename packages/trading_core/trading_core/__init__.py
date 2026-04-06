"""Trading Core Shared Package."""

from trading_core.auth import auth_manager as AuthManager
from trading_core.providers import get_adapter
from trading_core.db import DatabaseManager
from trading_core.config import DB_URL
