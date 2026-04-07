import os
import asyncio
import json
import asyncpg
import threading
from typing import Optional, List, Dict
from datetime import datetime, timezone
from fyers_apiv3.FyersWebsocket.data_ws import FyersDataSocket

from trading_core.providers import registry, get_adapter
from trading_core.db import DatabaseManager
from trading_core.config import DB_URL, FYERS_CLIENT_ID

class LiveTickRecorder:
    def __init__(self, default_provider: str = "fyers"):
        self.provider_name = default_provider.lower()
        self.adapter = get_adapter(self.provider_name)
        self.symbols = []
        self.fyers_socket = None
        self.upstox_streamer = None
        self.is_running = False
        self.tick_buffer = []
        self.buffer_lock = threading.Lock()
        self.event_queue = asyncio.Queue()
        self._ws_connected = False

    async def connect_db(self):
        pool = await DatabaseManager.get_pool()
        return pool

    async def save_ticks_to_db(self):
        while self.is_running:
            await asyncio.sleep(5)
            with self.buffer_lock:
                if not self.tick_buffer: continue
                current_batch, self.tick_buffer = self.tick_buffer.copy(), []
            
            pool = await self.connect_db()
            async with pool.acquire() as conn:
                table = f"broker_{self.provider_name}.market_ticks"
                await conn.executemany(f"INSERT INTO {table} (time, symbol, price, volume, bid, ask) VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING", 
                                      [(t[0], t[1], t[2], t[3], t[4], t[5]) for t in current_batch])
                # Broadcast
                await self.event_queue.put({"type": "save", "ticks": len(current_batch), "symbols": len(set(t[1] for t in current_batch))})

    def _on_fyers_message(self, message):
        if not isinstance(message, dict) or message.get("type") in ("cn", "ful", "sub"): return
        
        # Fyers LiteMode=False provides rich market depth via these standard internal keys
        vol = message.get("vol_traded_today", message.get("v", 0))
        bid = message.get("bid_price", message.get("bp1", 0.0))
        ask = message.get("ask_price", message.get("ap1", 0.0))
        
        # Complex tick capture
        self.tick_buffer.append((datetime.now(timezone.utc), message.get("symbol"), message.get("ltp"), vol, bid, ask))

    async def start(self, provider: str = "fyers"):
        if self.is_running: return "Already running"
        self.provider_name = provider.lower()
        self.adapter = get_adapter(self.provider_name)
        
        if not self.adapter.validate_token(): return "Token invalid"
        
        self.is_running = True
        asyncio.create_task(self.save_ticks_to_db())
        
        if self.provider_name == "fyers":
            ws_token = f"{FYERS_CLIENT_ID}:{self.adapter._access_token}"
            self.fyers_socket = FyersDataSocket(
                access_token=ws_token, log_path="", litemode=False,
                on_connect=self._on_open, on_message=self._on_fyers_message
            )
            threading.Thread(target=self.fyers_socket.connect, daemon=True).start()
        return "Started"

    def _on_open(self):
        self._ws_connected = True
        if self.symbols: self.fyers_socket.subscribe(self.symbols, data_type="SymbolUpdate")

    async def stop(self, provider=None):
        self.is_running = False
        if self.fyers_socket: self.fyers_socket.close_connection()
        return "Stopped"

    async def subscribe(self, symbols: List[str]):
        added = []
        for s in symbols:
            if s not in self.symbols:
                self.symbols.append(s)
                added.append(s)
        
        if self._ws_connected and added:
            if self.provider_name == "fyers":
                self.fyers_socket.subscribe(added, data_type="SymbolUpdate")
        return self.symbols

    async def unsubscribe(self, symbols: List[str]):
        removed = []
        for s in symbols:
            if s in self.symbols:
                self.symbols.remove(s)
                removed.append(s)
        
        if self._ws_connected and removed:
            if self.provider_name == "fyers":
                self.fyers_socket.unsubscribe(removed, data_type="SymbolUpdate")
        return self.symbols

    def get_status(self):
        return {
            "is_running": self.is_running,
            "provider": self.provider_name,
            "symbols": self.symbols,
            "ws_connected": self._ws_connected
        }

    async def event_generator(self):
        while True:
            event = await self.event_queue.get()
            yield f"data: {json.dumps(event)}\n\n"

class MultiProviderRecorderManager:
    def __init__(self):
        self._recorders = {"fyers": LiveTickRecorder("fyers"), "upstox": LiveTickRecorder("upstox")}
    async def start(self, p): return await self._recorders[p.lower()].start(p)
    async def stop(self, p): return await self._recorders[p.lower()].stop()
    async def subscribe(self, p, s): return await self._recorders[p.lower()].subscribe(s)
    async def unsubscribe(self, p, s): return await self._recorders[p.lower()].unsubscribe(s)
    def get_status(self, p): return self._recorders[p.lower()].get_status()
    async def event_generator(self, p):
        async for e in self._recorders[p.lower()].event_generator(): yield e

recorder_manager = MultiProviderRecorderManager()
