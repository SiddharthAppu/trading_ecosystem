import asyncio
import os
import json
import websockets
from datetime import datetime
from trading_core.db import DatabaseManager
from trading_core.config import DB_URL

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
    elif data_type == "options_ohlc":
        return f"{schema}.options_ohlc"
    else:
        raise ValueError(f"Unsupported data_type: {data_type}")

def get_columns_for_type(data_type: str) -> str:
    """Get SELECT clause columns based on data_type."""
    if data_type == "market_ticks":
        return "time, symbol, price, volume, bid, ask"
    elif data_type == "ohlcv_1m":
        return "time, symbol, open, high, low, close, volume"
    elif data_type == "options_ohlc":
        return "time, symbol, open, high, low, close, volume, calc_implied_volatility AS implied_volatility, calc_delta AS delta"
    else:
        raise ValueError(f"Unsupported data_type: {data_type}")

async def fetch_historical_series(
    symbol: str,
    provider: str = "fyers",
    data_type: str = "options_ohlc",
    start_time: str = None,
    end_time: str = None
):
    """
    Fetch historical data from database.
    
    Args:
        symbol: Trading symbol
        provider: "fyers" or "upstox"
        data_type: "market_ticks", "ohlcv_1m", or "options_ohlc"
        start_time: ISO format start time (optional)
        end_time: ISO format end time (optional)
    """
    pool = await DatabaseManager.get_pool()
    table = get_table_name(data_type, provider)
    columns = get_columns_for_type(data_type)
    
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
        
        query = f"""
            SELECT {columns}
            FROM {table}
            {where_clause}
            ORDER BY time ASC;
        """
        
        records = await conn.fetch(query, *params)
        return [dict(r) for r in records]

async def replay_handler(websocket):
    print("Client connected to Replay Engine")
    try:
        config_msg = await websocket.recv()
        config = json.loads(config_msg)
        
        # Extract configuration parameters
        symbol = config.get("symbol")
        provider = config.get("provider", "fyers")
        data_type = config.get("data_type", "options_ohlc")  # market_ticks, ohlcv_1m, options_ohlc
        speed = config.get("speed", 1.0)
        start_time = config.get("start_time")  # ISO format: "2025-01-01T09:15:00Z"
        end_time = config.get("end_time")      # ISO format: "2025-01-31T15:30:00Z"
        
        if not symbol:
            await websocket.send(json.dumps({"error": "Symbol is required"}))
            return
        
        # Validate data_type
        try:
            get_table_name(data_type, provider)
        except ValueError as e:
            await websocket.send(json.dumps({"error": str(e)}))
            return
            
        print(f"Streaming replay: symbol={symbol}, provider={provider}, data_type={data_type}, speed={speed}x")
        if start_time or end_time:
            print(f"  Time range: {start_time or 'start'} to {end_time or 'end'}")
        
        try:
            data = await fetch_historical_series(symbol, provider, data_type, start_time, end_time)
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
        except:
            pass

async def main():
    print("Starting Replay Server on ws://localhost:8765")
    async with websockets.serve(replay_handler, "localhost", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
