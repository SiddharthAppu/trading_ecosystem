import asyncio
import json
import websockets
from aiohttp import web
from trading_core.db import DatabaseManager



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




def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _json_cors(payload: dict, status: int = 200) -> web.Response:
    return web.json_response(payload, status=status, headers=_cors_headers())

async def fetch_historical_series(
    symbol: str,
    provider: str = "fyers",
    data_type: str = "options_ohlc",
    start_time: str = None,
    end_time: str = None,
    timeframe: str = "1m",
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
                        time_bucket(
                            INTERVAL '{timeframe_minutes} minute',
                            time,
                            TIMESTAMPTZ '{MARKET_BUCKET_ORIGIN_UTC}'
                        ) AS bucket_time,
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
        start_time = config.get("start_time")  # ISO format: "2025-01-01T09:15:00Z"
        end_time = config.get("end_time")      # ISO format: "2025-01-31T15:30:00Z"
        
        if not symbol:
            await websocket.send(json.dumps({"error": "Symbol is required"}))
            return
        
        # Validate data_type
        try:
            get_table_name(data_type, provider)
            _parse_timeframe(timeframe)
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


async def load_replay_handler(request: web.Request) -> web.Response:
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=_cors_headers())

    query = request.query

    symbol = (query.get("symbol") or "").strip()
    provider = (query.get("provider") or "fyers").strip().lower()
    data_type = (query.get("data_type") or "options_ohlc").strip()
    timeframe = (query.get("timeframe") or "1m").strip().lower()
    start_time = (query.get("start_time") or "").strip() or None
    end_time = (query.get("end_time") or "").strip() or None

    if not symbol:
        return _json_cors({"error": "symbol is required"}, status=400)

    try:
        get_table_name(data_type, provider)
        _parse_timeframe(timeframe)
    except ValueError as e:
        return _json_cors({"error": str(e)}, status=400)

    try:
        rows = await fetch_historical_series(
            symbol=symbol,
            provider=provider,
            data_type=data_type,
            start_time=start_time,
            end_time=end_time,
            timeframe=timeframe,
        )
    except Exception as e:
        return _json_cors({"error": f"Database error: {str(e)}"}, status=500)

    for row in rows:
        row["time"] = row["time"].isoformat()

    return _json_cors({
        "status": "success",
        "symbol": symbol,
        "provider": provider,
        "data_type": data_type,
        "timeframe": timeframe,
        "record_count": len(rows),
        "records": rows,
    })


async def start_http_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/replay/load", load_replay_handler)
    app.router.add_options("/replay/load", load_replay_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 8766)
    await site.start()
    return runner

async def main():
    print("Starting Replay Server on ws://localhost:8765")
    print("Starting Replay HTTP API on http://localhost:8766/replay/load")
    http_runner = await start_http_server()
    try:
        async with websockets.serve(replay_handler, "localhost", 8765):
            await asyncio.Future()
    finally:
        await http_runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
