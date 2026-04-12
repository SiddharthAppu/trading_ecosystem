import asyncio
import json
import websockets
from trading_core.db import DatabaseManager


SUPPORTED_INDICATORS = {
    "ema_20",
    "sma_20",
    "rsi_14",
    "macd",
}


def _parse_indicators(raw_indicators) -> list[str]:
    if raw_indicators is None:
        return []
    if isinstance(raw_indicators, str):
        tokens = [t.strip().lower() for t in raw_indicators.split(",") if t.strip()]
    elif isinstance(raw_indicators, list):
        tokens = [str(t).strip().lower() for t in raw_indicators if str(t).strip()]
    else:
        raise ValueError("Indicators must be a comma-separated string or string array")

    deduped = []
    seen = set()
    for token in tokens:
        if token not in seen:
            deduped.append(token)
            seen.add(token)

    unsupported = [t for t in deduped if t not in SUPPORTED_INDICATORS]
    if unsupported:
        raise ValueError(
            "Unsupported indicators: " + ", ".join(unsupported) +
            ". Supported: " + ", ".join(sorted(SUPPORTED_INDICATORS))
        )

    return deduped


def _supports_indicators(data_type: str) -> bool:
    return data_type in ("ohlcv_1m", "ohlcv_1min_from_ticks", "options_ohlc")


def _to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _calc_sma(values: list[float | None], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    for idx in range(len(values)):
        if idx < period - 1:
            continue
        window = values[idx - period + 1: idx + 1]
        if any(v is None for v in window):
            continue
        output[idx] = sum(window) / period
    return output


def _calc_ema(values: list[float | None], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) < period:
        return output

    alpha = 2 / (period + 1)

    seed_start = None
    for idx in range(0, len(values) - period + 1):
        window = values[idx:idx + period]
        if all(v is not None for v in window):
            seed_start = idx
            break

    if seed_start is None:
        return output

    seed_window = values[seed_start:seed_start + period]
    ema_prev = sum(seed_window) / period
    seed_idx = seed_start + period - 1
    output[seed_idx] = ema_prev

    for idx in range(seed_idx + 1, len(values)):
        value = values[idx]
        if value is None:
            output[idx] = None
            continue
        ema_prev = (value * alpha) + (ema_prev * (1 - alpha))
        output[idx] = ema_prev

    return output


def _calc_rsi(values: list[float | None], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return output

    deltas: list[float | None] = [None]
    for idx in range(1, len(values)):
        prev_value = values[idx - 1]
        curr_value = values[idx]
        if prev_value is None or curr_value is None:
            deltas.append(None)
        else:
            deltas.append(curr_value - prev_value)

    seed = deltas[1:period + 1]
    if any(delta is None for delta in seed):
        return output

    gains = [max(delta, 0) for delta in seed if delta is not None]
    losses = [abs(min(delta, 0)) for delta in seed if delta is not None]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        output[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        output[period] = 100 - (100 / (1 + rs))

    for idx in range(period + 1, len(values)):
        delta = deltas[idx]
        if delta is None:
            output[idx] = None
            continue

        gain = max(delta, 0)
        loss = abs(min(delta, 0))
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        if avg_loss == 0:
            output[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            output[idx] = 100 - (100 / (1 + rs))

    return output


def _compute_indicators(rows: list[dict], indicators: list[str]) -> None:
    if not rows or not indicators:
        return

    closes = [_to_float(row.get("close")) for row in rows]

    ema20 = _calc_ema(closes, 20) if "ema_20" in indicators else None
    sma20 = _calc_sma(closes, 20) if "sma_20" in indicators else None
    rsi14 = _calc_rsi(closes, 14) if "rsi_14" in indicators else None

    macd_line = None
    macd_signal = None
    macd_histogram = None
    if "macd" in indicators:
        ema12 = _calc_ema(closes, 12)
        ema26 = _calc_ema(closes, 26)
        macd_line = []
        for idx in range(len(closes)):
            if ema12[idx] is None or ema26[idx] is None:
                macd_line.append(None)
            else:
                macd_line.append(ema12[idx] - ema26[idx])
        macd_signal = _calc_ema(macd_line, 9)
        macd_histogram = []
        for idx in range(len(closes)):
            if macd_line[idx] is None or macd_signal[idx] is None:
                macd_histogram.append(None)
            else:
                macd_histogram.append(macd_line[idx] - macd_signal[idx])

    for idx, row in enumerate(rows):
        if ema20 is not None:
            row["ema_20"] = ema20[idx]
        if sma20 is not None:
            row["sma_20"] = sma20[idx]
        if rsi14 is not None:
            row["rsi_14"] = rsi14[idx]
        if macd_line is not None:
            row["macd_line"] = macd_line[idx]
            row["macd_signal"] = macd_signal[idx]
            row["macd_histogram"] = macd_histogram[idx]

# Replay Server logic ported to the unified service structure
# Uses the DatabaseManager for connection pooling

def get_table_name(data_type: str = "options_ohlc", provider: str = "fyers") -> str:
    """Get the fully qualified table name based on data_type and provider."""
    p = (provider or "fyers").lower()
    schema = "broker_upstox" if p == "upstox" else "broker_fyers"
    
    if data_type == "market_ticks":
        return f"{schema}.market_ticks"
    elif data_type == "ohlcv_1m":
        return f"{schema}.ohlcv_1m"
    elif data_type == "ohlcv_1min_from_ticks":
        return f"{schema}.ohlcv_1min_from_ticks"
    elif data_type == "options_ohlc":
        return f"{schema}.options_ohlc"
    else:
        raise ValueError(f"Unsupported data_type: {data_type}")

def get_columns_for_type(data_type: str) -> str:
    """Get SELECT clause columns based on data_type."""
    if data_type == "market_ticks":
        return "time, symbol, price, volume, bid, ask"
    elif data_type in ("ohlcv_1m", "ohlcv_1min_from_ticks"):
        return "time, symbol, open, high, low, close, volume"
    elif data_type == "options_ohlc":
        return "time, symbol, open, high, low, close, volume, calc_implied_volatility AS implied_volatility, calc_delta AS delta"
    else:
        raise ValueError(f"Unsupported data_type: {data_type}")


def _parse_timeframe(timeframe: str | None) -> tuple[str, int]:
    tf = (timeframe or "1m").strip().lower()
    allowed = {
        "1m": 1,
        "5m": 5,
        "10m": 10,
    }
    if tf not in allowed:
        raise ValueError("Unsupported timeframe. Use one of: 1m, 5m, 10m")
    return tf, allowed[tf]


def _supports_timeframe_aggregation(data_type: str) -> bool:
    return data_type in ("ohlcv_1m", "ohlcv_1min_from_ticks")

async def fetch_historical_series(
    symbol: str,
    provider: str = "fyers",
    data_type: str = "options_ohlc",
    start_time: str = None,
    end_time: str = None,
    timeframe: str = "1m",
    indicators: list[str] | None = None,
):
    """
    Fetch historical data from database.
    
    Args:
        symbol: Trading symbol
        provider: "fyers" or "upstox"
        data_type: "market_ticks", "ohlcv_1m", "ohlcv_1min_from_ticks", or "options_ohlc"
        start_time: ISO format start time (optional)
        end_time: ISO format end time (optional)
    """
    pool = await DatabaseManager.get_pool()
    table = get_table_name(data_type, provider)
    columns = get_columns_for_type(data_type)
    parsed_timeframe, timeframe_minutes = _parse_timeframe(timeframe)

    if parsed_timeframe != "1m" and not _supports_timeframe_aggregation(data_type):
        raise ValueError(
            f"Timeframe aggregation is not supported for data_type={data_type}. "
            "Use 1m for this data type."
        )
    
    async with pool.acquire() as conn:
        # Build WHERE clause with optional time filters
        where_clause = "WHERE symbol = $1"
        params = [symbol]
        
        if start_time:
            params.append(start_time)
            where_clause += f" AND time >= ${len(params)}"
        
        if end_time:
            params.append(end_time)
            where_clause += f" AND time <= ${len(params)}"
        
        if parsed_timeframe == "1m":
            query = f"""
                SELECT {columns}
                FROM {table}
                {where_clause}
                ORDER BY time ASC;
            """
        else:
            query = f"""
                SELECT
                    bucket_time AS time,
                    symbol,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM (
                    SELECT
                        time_bucket(INTERVAL '{timeframe_minutes} minute', time) AS bucket_time,
                        symbol,
                        (array_agg(open ORDER BY time ASC))[1] AS open,
                        MAX(high) AS high,
                        MIN(low) AS low,
                        (array_agg(close ORDER BY time DESC))[1] AS close,
                        COALESCE(SUM(volume), 0)::bigint AS volume
                    FROM {table}
                    {where_clause}
                    GROUP BY 1, 2
                ) grouped
                ORDER BY time ASC;
            """
        
        records = await conn.fetch(query, *params)
        rows = [dict(r) for r in records]

    if indicators:
        _compute_indicators(rows, indicators)

    return rows

async def replay_handler(websocket):
    print("Client connected to Replay Engine")
    try:
        config_msg = await websocket.recv()
        config = json.loads(config_msg)
        
        # Extract configuration parameters
        symbol = config.get("symbol")
        provider = config.get("provider", "fyers")
        data_type = config.get("data_type", "options_ohlc")  # market_ticks, ohlcv_1m, ohlcv_1min_from_ticks, options_ohlc
        speed = config.get("speed", 1.0)
        timeframe = config.get("timeframe", "1m")
        indicators = config.get("indicators", [])
        start_time = config.get("start_time")  # ISO format: "2025-01-01T09:15:00Z"
        end_time = config.get("end_time")      # ISO format: "2025-01-31T15:30:00Z"
        
        if not symbol:
            await websocket.send(json.dumps({"error": "Symbol is required"}))
            return
        
        # Validate data_type
        try:
            get_table_name(data_type, provider)
            _parse_timeframe(timeframe)
            parsed_indicators = _parse_indicators(indicators)
            if parsed_indicators and not _supports_indicators(data_type):
                raise ValueError(
                    f"Indicators are not supported for data_type={data_type}. "
                    "Use ohlcv_1m, ohlcv_1min_from_ticks, or options_ohlc."
                )
        except ValueError as e:
            await websocket.send(json.dumps({"error": str(e)}))
            return
            
        source_table = get_table_name(data_type, provider)
        print(
            f"Streaming replay: symbol={symbol}, provider={provider}, data_type={data_type}, "
            f"timeframe={timeframe}, speed={speed}x"
        )
        if start_time or end_time:
            print(f"  Time range: {start_time or 'start'} to {end_time or 'end'}")
        
        try:
            data = await fetch_historical_series(
                symbol,
                provider,
                data_type,
                start_time,
                end_time,
                timeframe,
                parsed_indicators,
            )
        except Exception as e:
            await websocket.send(json.dumps({"error": f"Database error: {str(e)}"}))
            return
        
        if not data:
            await websocket.send(json.dumps({"status": "no_data", "message": f"No data found for {symbol}"}))
            return
        
        # Send metadata
        await websocket.send(json.dumps({
            "status": "started",
            "symbol": symbol,
            "data_type": data_type,
            "timeframe": timeframe,
            "source_table": source_table,
            "indicators": parsed_indicators,
            "record_count": len(data),
            "speed": speed
        }))
        
        # Stream the data
        for row in data:
            row["time"] = row["time"].isoformat()
            await websocket.send(json.dumps(row))
            # Replay speed: 1x = 1 bar per second (configurable)
            await asyncio.sleep(1.0 / float(speed))
            
        await websocket.send(json.dumps({"status": "completed"}))
        print(f"Replay completed for {symbol}")
        
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    except Exception as e:
        print(f"Replay Error: {e}")
        try:
            await websocket.send(json.dumps({"error": f"Server error: {str(e)}"}))
        except Exception:
            pass

async def main():
    print("Starting Replay Server on ws://localhost:8765")
    async with websockets.serve(replay_handler, "localhost", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
