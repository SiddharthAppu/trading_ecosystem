-- Add Greeks columns to provider history tables if they exist.
-- Includes both legacy table names and current broker schema tables.

ALTER TABLE IF EXISTS public.upstox_history
    ADD COLUMN IF NOT EXISTS delta DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS theta DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS gamma DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS vega DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS iv DOUBLE PRECISION;

ALTER TABLE IF EXISTS public.fyers_history
    ADD COLUMN IF NOT EXISTS delta DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS theta DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS gamma DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS vega DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS iv DOUBLE PRECISION;

ALTER TABLE IF EXISTS broker_upstox.options_ohlc
    ADD COLUMN IF NOT EXISTS delta DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS theta DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS gamma DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS vega DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS iv DOUBLE PRECISION;

ALTER TABLE IF EXISTS broker_fyers.options_ohlc
    ADD COLUMN IF NOT EXISTS delta DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS theta DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS gamma DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS vega DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS iv DOUBLE PRECISION;

-- Enable TimescaleDB compression where tables are hypertables.
ALTER TABLE IF EXISTS public.upstox_history
    SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'symbol',
        timescaledb.compress_orderby = 'time DESC'
    );

ALTER TABLE IF EXISTS public.fyers_history
    SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'symbol',
        timescaledb.compress_orderby = 'time DESC'
    );

ALTER TABLE IF EXISTS broker_upstox.options_ohlc
    SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'symbol',
        timescaledb.compress_orderby = 'time DESC'
    );

ALTER TABLE IF EXISTS broker_fyers.options_ohlc
    SET (
        timescaledb.compress,
        timescaledb.compress_segmentby = 'symbol',
        timescaledb.compress_orderby = 'time DESC'
    );

-- Optional compression policy (example: compress chunks older than 1 day).
SELECT add_compression_policy('broker_upstox.options_ohlc', INTERVAL '1 day')
WHERE to_regclass('broker_upstox.options_ohlc') IS NOT NULL;

SELECT add_compression_policy('broker_fyers.options_ohlc', INTERVAL '1 day')
WHERE to_regclass('broker_fyers.options_ohlc') IS NOT NULL;
