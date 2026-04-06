import asyncio
import os
import json
import websockets
from datetime import datetime
from trading_core.db import DatabaseManager
from trading_core.config import DB_URL

# Replay Server logic ported to the unified service structure
# Uses the DatabaseManager for connection pooling

def get_ohlc_table(provider: str = "fyers") -> str:
    p = (provider or "fyers").lower()
    if p == "upstox":
        return "broker_upstox.options_ohlc"
    return "broker_fyers.options_ohlc"

async def fetch_historical_series(symbol: str, provider: str = "fyers"):
    pool = await DatabaseManager.get_pool()
    table = get_ohlc_table(provider)
    
    async with pool.acquire() as conn:
        records = await conn.fetch(f"""
            SELECT time, provider_symbol AS symbol, open, high, low, close, volume,
                   calculated_implied_volatility AS implied_volatility,
                   calculated_delta AS delta
            FROM {table}
            WHERE provider_symbol = $1
            ORDER BY time ASC;
        """, symbol)
        return [dict(r) for r in records]

async def replay_handler(websocket):
    print("Client connected to Replay Engine")
    try:
        config_msg = await websocket.recv()
        config = json.loads(config_msg)
        symbol, provider, speed = config.get("symbol"), config.get("provider", "fyers"), config.get("speed", 1.0)
        
        if not symbol:
            await websocket.send(json.dumps({"error": "Symbol missing"}))
            return
            
        print(f"Streaming replay for {symbol} at {speed}x speed")
        data = await fetch_historical_series(symbol, provider)
        
        for row in data:
            row["time"] = row["time"].isoformat()
            await websocket.send(json.dumps(row))
            # 60s per bar / speed
            await asyncio.sleep(1.0 / float(speed))
            
        await websocket.send(json.dumps({"status": "completed"}))
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    except Exception as e:
        print(f"Replay Error: {e}")

async def main():
    print("Starting Replay Server on ws://localhost:8765")
    async with websockets.serve(replay_handler, "localhost", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
