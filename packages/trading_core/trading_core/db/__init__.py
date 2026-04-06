import os
import asyncpg
from dotenv import load_dotenv

# Path to the centralized .env in the monorepo config
CONFIG_DIR = os.getenv("TRADING_CONFIG_DIR", os.path.join(os.getcwd(), "config"))
ENV_FILE = os.path.join(CONFIG_DIR, ".env")

if os.path.exists(ENV_FILE):
    load_dotenv(ENV_FILE)

DB_URL = os.getenv("DATABASE_URL")

class DatabaseManager:
    """Manages TimescaleDB connections for all services."""
    
    _pool = None

    @classmethod
    async def get_pool(cls):
        if cls._pool is None:
            if not DB_URL:
                raise ValueError(f"DATABASE_URL not found in {ENV_FILE}")
            cls._pool = await asyncpg.create_pool(DB_URL)
        return cls._pool

    @classmethod
    async def close_pool(cls):
        if cls._pool:
            await cls._pool.close()
            cls._pool = None

from trading_core.db.migrations import MigrationManager
