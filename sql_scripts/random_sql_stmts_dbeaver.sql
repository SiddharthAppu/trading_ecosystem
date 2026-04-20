SELECT symbol 
FROM broker_upstox.ohlcv_1m
INTERSECT
SELECT symbol 
FROM broker_upstox.options_ohlc;

SELECT 
    a.time, 
    a.symbol, 
    a.close AS ohlcv_close, 
    b.close AS options_close
FROM broker_upstox.ohlcv_1m a
INNER JOIN broker_upstox.options_ohlc b 
    ON a.time = b.time 
    AND a.symbol = b.symbol
ORDER BY a.time DESC
LIMIT 100;

-- common symbol between broker_fyers.ohlcv_1m and broker_upstox.ohlcv_1m
SELECT symbol 
FROM broker_fyers.ohlcv_1m
INTERSECT
SELECT symbol 
FROM broker_upstox.ohlcv_1m;

-- overlapping period between broker_fyers.ohlcv_1m and broker_upstox.ohlcv_1m
SELECT 
    f.symbol,
    MIN(f.time) AS overlap_start,
    MAX(f.time) AS overlap_end,
    COUNT(*) AS common_row_count
FROM broker_fyers.ohlcv_1m f
INNER JOIN broker_upstox.ohlcv_1m u 
    ON f.time = u.time 
    AND f.symbol = u.symbol
GROUP BY f.symbol
ORDER BY overlap_start ASC;


SELECT 
    f.time,
    -- Check Close Price (The most critical for your indicators)
    ABS(f.close - u.close) as close_diff,
    -- Check Volume (Often the most inconsistent between brokers)
    ABS(f.volume - u.volume) as vol_diff,
    -- Flag rows where ANY OHLC value differs by more than 0.01
    CASE 
        WHEN ABS(f.open - u.open) > 0.01 OR 
             ABS(f.high - u.high) > 0.01 OR 
             ABS(f.low - u.low) > 0.01 OR 
             ABS(f.close - u.close) > 0.01 
        THEN 'PRICE_MISMATCH'
        WHEN f.volume != u.volume THEN 'VOLUME_MISMATCH'
        ELSE 'MATCH'
    END as status
FROM broker_fyers.ohlcv_1m f
INNER JOIN broker_upstox.ohlcv_1m u 
    ON f.time = u.time AND f.symbol = u.symbol
WHERE f.symbol = 'NSE:NIFTY50-INDEX'
  AND (ABS(f.close - u.close) > 0.01 OR f.volume != u.volume)
ORDER BY f.time DESC
LIMIT 100;



SELECT 
    f.time,
    f.close AS fyers_close,
    u.close AS upstox_close,
    ABS(f.close - u.close) AS absolute_diff
FROM broker_fyers.ohlcv_1m f
INNER JOIN broker_upstox.ohlcv_1m u 
    ON f.time = u.time AND f.symbol = u.symbol
WHERE f.symbol = 'NSE:NIFTY50-INDEX'
  AND ABS(f.close - u.close) > 0.5 -- Only show differences > 0.5 points
ORDER BY absolute_diff DESC;


