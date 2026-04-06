import asyncio
import logging
from trading_core.db import DatabaseManager

logger = logging.getLogger(__name__)

class MigrationManager:
    """Handles schema and table creation for TimescaleDB."""

    SCHEMA_SQL = """
    CREATE SCHEMA IF NOT EXISTS broker_fyers;
    CREATE SCHEMA IF NOT EXISTS broker_upstox;
    CREATE SCHEMA IF NOT EXISTS analytics;
    """

    TABLE_SQL = """
    -- Market Ticks Table (Hypertable)
    CREATE TABLE IF NOT EXISTS broker_fyers.market_ticks (
        time TIMESTAMPTZ NOT NULL,
        symbol TEXT NOT NULL,
        price DOUBLE PRECISION,
        volume BIGINT,
        bid DOUBLE PRECISION,
        ask DOUBLE PRECISION
    );
    SELECT create_hypertable('broker_fyers.market_ticks', 'time', if_not_exists => TRUE);

    CREATE TABLE IF NOT EXISTS broker_upstox.market_ticks (
        time TIMESTAMPTZ NOT NULL,
        symbol TEXT NOT NULL,
        price DOUBLE PRECISION,
        volume BIGINT,
        bid DOUBLE PRECISION,
        ask DOUBLE PRECISION
    );
    SELECT create_hypertable('broker_upstox.market_ticks', 'time', if_not_exists => TRUE);

    -- 1m OHLCV Table (Hypertable)
    CREATE TABLE IF NOT EXISTS broker_fyers.ohlcv_1m (
        time TIMESTAMPTZ NOT NULL,
        symbol TEXT NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        volume BIGINT
    );
    SELECT create_hypertable('broker_fyers.ohlcv_1m', 'time', if_not_exists => TRUE);

    CREATE TABLE IF NOT EXISTS broker_upstox.ohlcv_1m (
        time TIMESTAMPTZ NOT NULL,
        symbol TEXT NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        volume BIGINT
    );
    SELECT create_hypertable('broker_upstox.ohlcv_1m', 'time', if_not_exists => TRUE);

    -- Options Greeks Table (Hypertable)
    CREATE TABLE IF NOT EXISTS analytics.options_greeks (
        time TIMESTAMPTZ NOT NULL,
        symbol TEXT NOT NULL,
        underlying_price DOUBLE PRECISION,
        strike DOUBLE PRECISION,
        expiry DATE,
        option_type TEXT,
        iv DOUBLE PRECISION,
        delta DOUBLE PRECISION,
        gamma DOUBLE PRECISION,
        theta DOUBLE PRECISION,
        vega DOUBLE PRECISION,
        rho DOUBLE PRECISION
    );
    SELECT create_hypertable('analytics.options_greeks', 'time', if_not_exists => TRUE);
    """

    @classmethod
    async def run_migrations(cls):
        """Initializes schemas and hypertables."""
        logger.info("Starting database migrations...")
        pool = await DatabaseManager.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # 1. Create schemas
                await conn.execute(cls.SCHEMA_SQL)
                logger.info("Schemas created successfully.")
                
                # 2. Create tables and hypertables
                # We split by semicolon because SELECT create_hypertable might fail in some contexts if not careful
                # Note: asyncpg allows multiple statements in one execute()
                await conn.execute(cls.TABLE_SQL)
                logger.info("Tables and Hypertables initialized successfully.")

if __name__ == "__main__":
    # Test run
    logging.basicConfig(level=logging.INFO)
    asyncio.run(MigrationManager.run_migrations())
