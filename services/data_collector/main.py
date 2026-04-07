import os
import uvicorn
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import asyncpg

from trading_core.providers import get_adapter
from trading_core.analytics import OptionGreeks
from trading_core.db import DatabaseManager
from trading_core.config import DB_URL

# These will be the core background logic modules for the service
# I'll create these in the next file write
from services.data_collector.live_recorder import recorder_manager

app = FastAPI(title="Unified Data Collector API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DownloadRequest(BaseModel):
    option_symbol: str
    underlying_symbol: str
    start_date: str
    end_date: str
    strike: float
    option_type: str
    expiry_date: str
    provider: str = "fyers"

class SubscribeRequest(BaseModel):
    symbols: List[str]
    provider: str = "fyers"

class ChainRequest(BaseModel):
    underlying_symbol: str
    expiry_date: str
    strike_count: int = 10
    provider: str = "fyers"

@app.on_event("startup")
async def startup_event():
    await DatabaseManager.get_pool()
    from trading_core.db import MigrationManager
    await MigrationManager.run_migrations()

@app.on_event("shutdown")
async def shutdown_event():
    await DatabaseManager.close_pool()

@app.get("/auth/status")
async def auth_status(provider: str = "fyers"):
    adapter = get_adapter(provider)
    return {"authenticated": adapter.validate_token()}

@app.get("/auth/url")
async def auth_url(provider: str = "fyers"):
    adapter = get_adapter(provider)
    return {"url": adapter.generate_auth_link()}

@app.post("/download")
async def download_symbol(req: DownloadRequest):
    adapter = get_adapter(req.provider)
    
    try:
        # 1. Fetch Historical OHLC for Option and Spot
        option_ohlc = adapter.get_historical_data(req.option_symbol, req.start_date, req.end_date)
        spot_ohlc = adapter.get_historical_data(req.underlying_symbol, req.start_date, req.end_date)
        
        if not option_ohlc or not spot_ohlc:
            raise HTTPException(400, "Incomplete data returned for symbols.")
            
        # 2. Extract Greeks (Simplified logic for now, using the new core)
        # Note: In the future, I'll extract these to a background task
        
        # 3. Store to DB (I'll need to port the DB insert logic to the core)
        return {"status": "success", "count": len(option_ohlc)}
        
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/recorder/start")
async def start_recorder(provider: str = "fyers"):
    status = await recorder_manager.start(provider)
    return {"status": status}

@app.post("/recorder/stop")
async def stop_recorder(provider: str = "fyers"):
    status = await recorder_manager.stop(provider)
    return {"status": status}

@app.get("/recorder/status")
async def recorder_status(provider: str = "fyers"):
    return recorder_manager.get_status(provider)

@app.post("/recorder/subscribe")
async def subscribe_recorder(req: SubscribeRequest):
    symbols = await recorder_manager.subscribe(req.provider, req.symbols)
    return {"status": "success", "symbols": symbols}

@app.post("/recorder/unsubscribe")
async def unsubscribe_recorder(req: SubscribeRequest):
    symbols = await recorder_manager.unsubscribe(req.provider, req.symbols)
    return {"status": "success", "symbols": symbols}

@app.post("/chain/generate")
async def generate_chain(req: ChainRequest):
    adapter = get_adapter(req.provider)
    try:
        data = adapter.get_option_chain_symbols(req.underlying_symbol, req.expiry_date, req.strike_count)
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/index-ticks/recent")
async def get_recent_index_ticks(limit: int = 20, provider: str = "fyers"):
    pool = await DatabaseManager.get_pool()
    table = f"broker_{provider}.market_ticks"
    try:
        async with pool.acquire() as conn:
            records = await conn.fetch(f"SELECT * FROM {table} ORDER BY time DESC LIMIT $1", limit)
            return {"status": "success", "ticks": [dict(r) for r in records]}
    except Exception as e:
        return {"status": "error", "message": str(e), "ticks": []}

@app.get("/recorder/events")
async def recorder_events(provider: str = "fyers"):
    return StreamingResponse(recorder_manager.event_generator(provider), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
