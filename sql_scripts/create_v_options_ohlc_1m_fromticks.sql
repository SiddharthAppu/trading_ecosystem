-- Creates a replay/backtest-friendly options view from tick-derived 1m bars.
-- Source lineage:
--   broker_upstox.market_ticks -> broker_upstox.ohlcv_1min_from_ticks (EOD aggregation)
--   + master_broker.symbol_master metadata join

CREATE SCHEMA IF NOT EXISTS master_broker;

CREATE OR REPLACE VIEW master_broker.v_options_ohlc_1m_fromticks AS
WITH option_bars AS (
    SELECT
        t.time,
        t.symbol AS upstox_key,
        t.open,
        t.high,
        t.low,
        t.close,
        t.volume
    FROM broker_upstox.ohlcv_1min_from_ticks t
    WHERE t.symbol LIKE 'NSE_FO|%'
),
index_bars AS (
    SELECT
        i.time,
        i.close AS nifty_spot
    FROM broker_upstox.ohlcv_1min_from_ticks i
    WHERE i.symbol = 'NSE_INDEX|Nifty 50'
)
SELECT
    ob.time,
    sm.human_symbol AS symbol,
    ob.open,
    ob.high,
    ob.low,
    ob.close,
    ob.volume,
    sm.expiry_date,
    sm.strike_price,
    COALESCE(
        NULLIF((to_jsonb(sm) ->> 'option_type'), ''),
        CASE
            WHEN sm.human_symbol LIKE '%_CE' THEN 'CE'
            WHEN sm.human_symbol LIKE '%_PE' THEN 'PE'
            ELSE NULL
        END
    ) AS option_type,
    ib.nifty_spot
FROM option_bars ob
JOIN master_broker.symbol_master sm
  ON sm.upstox_key = ob.upstox_key
LEFT JOIN index_bars ib
  ON ib.time = ob.time;
