import os
import asyncpg
from dotenv import load_dotenv

# Path to the centralized .env in the monorepo config
CONFIG_DIR = os.getenv("TRADING_CONFIG_DIR", os.path.join(os.getcwd(), "config"))
ENV_FILE = os.path.join(CONFIG_DIR, ".env")

if os.path.exists(ENV_FILE):
    load_dotenv(ENV_FILE)

DB_URL = os.getenv("DATABASE_URL")

import logging

logger = logging.getLogger("trading_core.db")

class DatabaseManager:
    """Manages TimescaleDB connections for all services."""
    
    _pool = None

    @classmethod
    async def get_pool(cls):
        if cls._pool is None:
            if not DB_URL:
                logger.warning("DATABASE_URL not found. Database operations will be disabled (Zero-DB Mode).")
                return None
            try:
                cls._pool = await asyncpg.create_pool(DB_URL)
            except Exception as e:
                logger.error(f"Failed to connect to database: {e}. Proceeding in Zero-DB Mode.")
                return None
        return cls._pool

    @classmethod
    async def close_pool(cls):
        if cls._pool:
            await cls._pool.close()
            cls._pool = None

from trading_core.db.migrations import MigrationManager
