-- 1. Create the schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS master_broker;

-- 2. Create the unified table
CREATE TABLE master_broker.ohlcv_1m (
    time            TIMESTAMPTZ NOT NULL,
    symbol          TEXT NOT NULL,
    -- Fyers Columns
    open_fyers      NUMERIC,
    high_fyers      NUMERIC,
    low_fyers       NUMERIC,
    close_fyers     NUMERIC,
    vol_fyers       NUMERIC,
    -- Upstox Columns
    open_upstox     NUMERIC,
    high_upstox     NUMERIC,
    low_upstox      NUMERIC,
    close_upstox    NUMERIC,
    vol_upstox      NUMERIC,
    -- Calculation Columns
    master_close    NUMERIC,
    is_outlier      BOOLEAN DEFAULT FALSE
);

-- 3. Convert to TimescaleDB Hypertable (Critical for performance)
SELECT create_hypertable('master_broker.ohlcv_1m', 'time');

-- 4. Create an index on symbol + time for fast Replay Studio lookups
CREATE INDEX idx_master_symbol_time ON master_broker.ohlcv_1m (symbol, time DESC);


-- This query uses a FULL OUTER JOIN to merge your existing data. It handles cases where one broker might have missed a minute that the other captured.
INSERT INTO master_broker.ohlcv_1m (
    time, symbol, 
    open_fyers, high_fyers, low_fyers, close_fyers, vol_fyers,
    open_upstox, high_upstox, low_upstox, close_upstox, vol_upstox,
    master_close
)
SELECT 
    COALESCE(f.time, u.time) as time,
    COALESCE(f.symbol, u.symbol) as symbol,
    -- Fyers Data
    f.open, f.high, f.low, f.close, f.volume,
    -- Upstox Data
    u.open, u.high, u.low, u.close, u.volume,
    -- Set Master Close (Prefer Upstox for Greeks, fallback to Fyers)
    COALESCE(u.close, f.close) as master_close
FROM broker_fyers.ohlcv_1m f
FULL OUTER JOIN broker_upstox.ohlcv_1m u 
    ON f.time = u.time AND f.symbol = u.symbol
WHERE f.symbol = 'NSE:NIFTY50-INDEX' OR u.symbol = 'NSE:NIFTY50-INDEX';



-- The "Delta Momentum" Validation After running the merge, you can run this quick audit to see if your "Master Feed" is stable.
-- Check for rows where the two brokers differed by more than 5 points
UPDATE master_broker.ohlcv_1m
SET is_outlier = TRUE
WHERE ABS(close_fyers - close_upstox) > 5.0;

-- Summary count of your new Replay DB
SELECT 
    COUNT(*) as total_minutes,
    COUNT(*) FILTER (WHERE is_outlier) as outlier_count,
    MIN(time) as start_date,
    MAX(time) as end_date
FROM master_broker.ohlcv_1m;



------------------------------

-- copy broker_upstox.options_ohlc into a new master_broker.options_ohlc_1m_fromupstox 
CREATE TABLE master_broker.options_ohlc_1m_fromupstox (
    time            TIMESTAMPTZ NOT NULL,
    symbol          TEXT NOT NULL,
    open            NUMERIC,
    high            NUMERIC,
    low             NUMERIC,
    close           NUMERIC,
    volume          NUMERIC,
    -- Greeks (to be populated by your Python script)
    calc_iv         NUMERIC,
    calc_delta      NUMERIC,
    calc_theta      NUMERIC,
    calc_gamma      NUMERIC,
    -- Reference data for Greeks
    strike_price    NUMERIC,
    expiry_date     DATE,
    option_type     TEXT -- 'CE' or 'PE'
);

-- Convert to Hypertable for performance
SELECT create_hypertable('master_broker.options_ohlc_1m_fromupstox', 'time');

-- insert data from broker_upstox.options_ohlc into a new master_broker.options_ohlc_1m_fromupstox
-- and updating columns 
INSERT INTO master_broker.options_ohlc_1m_fromupstox (
    time, symbol, open, high, low, close, volume,
    strike_price, expiry_date, option_type
)
SELECT 
    time,
    symbol,
    open,
    high,
    low,
    close,
    volume,
    -- Extract Strike
    (substring(symbol FROM '(\d{5})'))::NUMERIC,
    -- Convert '17 APR 25' string to a pure DATE
    to_date(substring(symbol FROM '(\d{1,2}\s[A-Z]{3}\s\d{2})'), 'DD MON YY'),
    -- Extract Option Type
    substring(symbol FROM '(CE|PE)')
FROM broker_upstox.options_ohlc
WHERE symbol LIKE 'NIFTY%';


CREATE INDEX idx_options_symbol_time 
ON master_broker.options_ohlc_1m_fromupstox (symbol, time DESC);


-- verification audit
SELECT 
    symbol, 
    strike_price, 
    expiry_date, 
    option_type,
    count(*) as row_count
FROM master_broker.options_ohlc_1m_fromupstox
GROUP BY 1, 2, 3, 4
ORDER BY expiry_date ASC
LIMIT 10;



-- UPDATING SPOT PRICE FROM MASTER OHLCV_1m to options_oh1m_fromupstox
-- 1. Add the columns (Fast)
ALTER TABLE master_broker.options_ohlc_1m_fromupstox 
ADD COLUMN IF NOT EXISTS nifty_spot NUMERIC,
ADD COLUMN IF NOT EXISTS is_stale_spot BOOLEAN DEFAULT FALSE;

-- 2. Combined Sync (Faster and safer)
UPDATE master_broker.options_ohlc_1m_fromupstox opt
SET 
    nifty_spot = idx.master_close,
    is_stale_spot = (idx.high_fyers = idx.low_fyers OR idx.high_upstox = idx.low_upstox)
FROM master_broker.ohlcv_1m idx
WHERE opt.time = idx.time 
  AND idx.symbol = 'NSE:NIFTY50-INDEX'
  AND opt.nifty_spot IS NULL;


-- 1. Reset the flag just to be safe (Optional but clean)
UPDATE master_broker.options_ohlc_1m_fromupstox SET is_stale_spot = FALSE;

-- 2. Run the Full Sync without the NULL constraint
UPDATE master_broker.options_ohlc_1m_fromupstox opt
SET 
    nifty_spot = idx.master_close,
    is_stale_spot = (
        (idx.high_fyers = idx.low_fyers AND idx.open_fyers = idx.close_fyers) 
        OR 
        (idx.high_upstox = idx.low_upstox AND idx.open_upstox = idx.close_upstox)
    )
FROM master_broker.ohlcv_1m idx
WHERE opt.time = idx.time 
  AND idx.symbol = 'NSE:NIFTY50-INDEX';


-- This forces an update on all 693k rows to ensure flags are accurate
UPDATE master_broker.options_ohlc_1m_fromupstox opt
SET 
    is_stale_spot = (
        (idx.high_fyers = idx.low_fyers AND idx.open_fyers = idx.close_fyers) 
        OR 
        (idx.high_upstox = idx.low_upstox AND idx.open_upstox = idx.close_upstox)
    )
FROM master_broker.ohlcv_1m idx
WHERE opt.time = idx.time 
  AND idx.symbol = 'NSE:NIFTY50-INDEX';


-- auditing
SELECT count(*) FROM master_broker.options_ohlc_1m_fromupstox WHERE nifty_spot IS NULL;

SELECT is_stale_spot, count(*) FROM master_broker.options_ohlc_1m_fromupstox GROUP BY 1;

SELECT time, symbol, nifty_spot, is_stale_spot FROM master_broker.options_ohlc_1m_fromupstox LIMIT 20;

SELECT is_stale_spot, count(*) FROM master_broker.options_ohlc_1m_fromupstox GROUP BY 1;

SELECT count(DISTINCT expiry_date) FROM master_broker.options_ohlc_1m_fromupstox;

SELECT symbol, count(*) FROM master_broker.options_ohlc_1m_fromupstox WHERE is_stale_spot = TRUE GROUP BY 1 ORDER BY 2 DESC LIMIT 10


SELECT time, symbol, (high_fyers - low_fyers) as spread
FROM master_broker.ohlcv_1m 
WHERE symbol = 'NSE:NIFTY50-INDEX'
  AND (high_fyers - low_fyers) < 0.05
  AND (high_fyers - low_fyers) > 0
LIMIT 10;

-- zero volume minutes
SELECT count(*) FROM master_broker.options_ohlc_1m_fromupstox WHERE volume = 0;

-- impossible prices
SELECT count(*) FROM master_broker.options_ohlc_1m_fromupstox WHERE close <= 0;

-- wide spreads
SELECT symbol, time, (high - low) as move FROM master_broker.options_ohlc_1m_fromupstox ORDER BY move DESC LIMIT 5;