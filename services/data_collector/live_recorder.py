import os
import asyncio
import json
import asyncpg
import threading
import logging
from typing import List, Any
from datetime import datetime, timezone
from fyers_apiv3.FyersWebsocket.data_ws import FyersDataSocket
import upstox_client

from trading_core.providers import registry, get_adapter
from trading_core.db import DatabaseManager
from trading_core.config import FYERS_CLIENT_ID
from trading_core.providers.upstox_adapter import UPSTOX_UNDERLYING_KEYS

logger = logging.getLogger(__name__)

class TickFileLogger:
    """Handles high-frequency tick logging to flat files."""
    def __init__(self, base_dir: str = "logs/ticks"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._locks = {}

    def _get_file_path(self, symbol: str):
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        clean_symbol = symbol.replace(":", "_").replace("-", "_")
        return self.base_dir / f"{clean_symbol}_{date_str}.csv"

    def log_ticks(self, rows: List[Any]):
        """Rows: (ts, symbol, price, volume, oi, delta, theta, bid, ask)"""
        grouped = {}
        for row in rows:
            symbol = row[1]
            grouped.setdefault(symbol, []).append(row)

        for symbol, ticks in grouped.items():
            path = self._get_file_path(symbol)
            is_new = not path.exists()
            
            with open(path, "a", encoding="utf-8") as f:
                if is_new:
                    f.write("timestamp,symbol,price,volume,oi,delta,theta,bid,ask\n")
                for t in ticks:
                    # ts, symbol, price, volume, oi, delta, theta, bid, ask
                    line = f"{t[0].isoformat()},{t[1]},{t[2]},{t[3]},{t[4]},{t[5]},{t[6]},{t[7]},{t[8]}\n"
                    f.write(line)

from pathlib import Path

class LiveTickRecorder:
    def __init__(self, default_provider: str = "fyers"):
        self.provider_name = default_provider.lower()
        self.adapter = get_adapter(self.provider_name)
        self.stream_mode = "lite"
        self.symbols = []
        self.fyers_socket = None
        self.upstox_streamer = None
        self._upstox_mode = None
        self.is_running = False
        self.tick_buffer = []
        self.greeks_buffer = []
        self.buffer_lock = threading.Lock()
        self.greeks_lock = threading.Lock()
        self.event_queue = asyncio.Queue()
        self._ws_connected = False
        self.file_logger = TickFileLogger()
        self.enable_db = True
        self.enable_file = True

    async def connect_db(self):
        try:
            pool = await DatabaseManager.get_pool()
            return pool
        except Exception:
            return None

    def _normalize_tick_row(self, row):
        # ts, symbol, price, volume, oi, delta, theta, bid, ask
        ts, symbol, price, volume, oi, delta, theta, bid, ask = row
        if not symbol or price is None:
            return None
        
        def _f(v, default=0.0):
            try: return float(v) if v is not None else default
            except: return default

        return (
            ts, str(symbol), _f(price), int(volume or 0), 
            int(oi or 0), _f(delta, None), _f(theta, None), 
            _f(bid), _f(ask)
        )

    def _normalize_greeks_row(self, row):
        ts, symbol, delta, theta, gamma, vega, iv = row
        if not symbol:
            return None

        def _to_float_or_none(value):
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        return (
            ts,
            str(symbol),
            _to_float_or_none(delta),
            _to_float_or_none(theta),
            _to_float_or_none(gamma),
            _to_float_or_none(vega),
            _to_float_or_none(iv),
        )

    async def save_ticks_to_db(self):
        while self.is_running:
            await asyncio.sleep(5)
            with self.buffer_lock:
                if not self.tick_buffer: continue
                current_batch, self.tick_buffer = self.tick_buffer.copy(), []

            valid_rows = []
            dropped_rows = 0
            for row in current_batch:
                normalized = self._normalize_tick_row(row)
                if normalized is None:
                    dropped_rows += 1
                    continue
                valid_rows.append(normalized)

            if not valid_rows:
                if dropped_rows:
                    await self.event_queue.put({"type": "save_drop", "provider": self.provider_name, "dropped": dropped_rows})
                continue

            # 1. File Logging (Astra Mode)
            if self.enable_file:
                try:
                    await asyncio.to_thread(self.file_logger.log_ticks, valid_rows)
                except Exception as e:
                    logger.error(f"File logging failed: {e}")

            # 2. DB Logging (Legacy Mode)
            if self.enable_db:
                try:
                    pool = await self.connect_db()
                    if pool:
                        async with pool.acquire() as conn:
                            table = f"broker_{self.provider_name}.market_ticks"
                            await conn.executemany(
                                f"INSERT INTO {table} (time, symbol, price, volume, bid, ask) VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING",
                                valid_rows,
                            )
                            await self.event_queue.put(
                                {
                                    "type": "save",
                                    "provider": self.provider_name,
                                    "ticks": len(valid_rows),
                                    "symbols": len(set(t[1] for t in valid_rows)),
                                    "dropped": dropped_rows,
                                }
                            )
                    else:
                        # Silently skip if DB is disabled/offline
                        pass
                except Exception as exc:
                    logger.exception("Tick persistence failed for provider=%s", self.provider_name)
                    await self.event_queue.put(
                        {
                            "type": "save_error",
                            "provider": self.provider_name,
                            "error": str(exc)[:300],
                            "ticks": len(valid_rows),
                        }
                    )

    async def save_greeks_to_db(self):
        while self.is_running:
            await asyncio.sleep(5)
            with self.greeks_lock:
                if not self.greeks_buffer:
                    continue
                current_batch, self.greeks_buffer = self.greeks_buffer.copy(), []

            valid_rows = []
            dropped_rows = 0
            for row in current_batch:
                normalized = self._normalize_greeks_row(row)
                if normalized is None:
                    dropped_rows += 1
                    continue
                valid_rows.append(normalized)

            if not valid_rows:
                continue

            if self.enable_db:
                try:
                    pool = await self.connect_db()
                    if pool:
                        async with pool.acquire() as conn:
                            table = f"broker_{self.provider_name}.options_greeks_live"
                            await conn.executemany(
                                f"""
                                INSERT INTO {table} (time, symbol, delta, theta, gamma, vega, iv)
                                VALUES ($1, $2, $3, $4, $5, $6, $7)
                                ON CONFLICT (time, symbol) DO UPDATE SET
                                    delta = EXCLUDED.delta,
                                    theta = EXCLUDED.theta,
                                    gamma = EXCLUDED.gamma,
                                    vega = EXCLUDED.vega,
                                    iv = EXCLUDED.iv
                                """,
                                valid_rows,
                            )
                            await self.event_queue.put(
                                {
                                    "type": "greeks_save",
                                    "provider": self.provider_name,
                                    "rows": len(valid_rows),
                                    "dropped": dropped_rows,
                                }
                            )
                except Exception as exc:
                    logger.exception("Greeks persistence failed for provider=%s", self.provider_name)
                    await self.event_queue.put(
                        {
                            "type": "greeks_save_error",
                            "provider": self.provider_name,
                            "error": str(exc)[:300],
                            "rows": len(valid_rows),
                        }
                    )

    def _on_fyers_message(self, message):
        if not isinstance(message, dict) or message.get("type") in ("cn", "ful", "sub"): return
        
        # Fyers LiteMode=False provides rich market depth via these standard internal keys
        # Complex tick capture: (ts, symbol, price, volume, oi, delta, theta, bid, ask)
        self.tick_buffer.append((
            datetime.now(timezone.utc), 
            message.get("symbol"), 
            message.get("ltp"), 
            vol, 
            message.get("oi", 0),
            message.get("delta"),
            message.get("theta"),
            bid, 
            ask
        ))

        greeks = {
            "delta": message.get("delta"),
            "theta": message.get("theta"),
            "gamma": message.get("gamma"),
            "vega": message.get("vega"),
            "iv": message.get("iv") or message.get("implied_volatility"),
        }
        if any(value is not None for value in greeks.values()):
            self.greeks_buffer.append(
                (
                    datetime.now(timezone.utc),
                    message.get("symbol"),
                    greeks["delta"],
                    greeks["theta"],
                    greeks["gamma"],
                    greeks["vega"],
                    greeks["iv"],
                )
            )

    def _nested_find_first(self, payload: Any, keys: tuple[str, ...]):
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if value is not None:
                    return value
            for value in payload.values():
                found = self._nested_find_first(value, keys)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = self._nested_find_first(item, keys)
                if found is not None:
                    return found
        return None

    def _extract_upstox_bid_ask(self, feed_payload: dict):
        quotes = self._nested_find_first(feed_payload, ("bidAskQuote", "bidsAndAsks", "quotes"))
        if isinstance(quotes, list) and quotes:
            top = quotes[0]
            if isinstance(top, dict):
                bid = top.get("bp") or top.get("bidP") or top.get("bidPrice") or top.get("bPrice")
                ask = top.get("ap") or top.get("askP") or top.get("askPrice") or top.get("aPrice")
                return bid or 0.0, ask or 0.0
        bid = self._nested_find_first(feed_payload, ("bp", "bidP", "bidPrice", "bPrice"))
        ask = self._nested_find_first(feed_payload, ("ap", "askP", "askPrice", "aPrice"))
        return bid or 0.0, ask or 0.0

    def _extract_upstox_greeks(self, feed_payload: dict):
        greeks = self._nested_find_first(feed_payload, ("optionGreeks", "greeks"))
        if not isinstance(greeks, dict):
            greeks = {}
        return {
            "delta": greeks.get("delta"),
            "theta": greeks.get("theta"),
            "gamma": greeks.get("gamma"),
            "vega": greeks.get("vega"),
            "iv": greeks.get("iv") or greeks.get("impliedVolatility"),
        }

    def _on_upstox_open(self, *_args):
        self._ws_connected = True
        if self.symbols and self.upstox_streamer and self._upstox_mode:
            try:
                self.upstox_streamer.subscribe(self.symbols, self._upstox_mode)
            except Exception:
                pass

    def _on_upstox_close(self, *_args):
        self._ws_connected = False

    def _on_upstox_error(self, *_args):
        self._ws_connected = False

    def _on_upstox_message(self, message):
        if not isinstance(message, dict):
            return

        feeds = message.get("feeds")
        if not isinstance(feeds, dict):
            return

        for instrument_key, feed_payload in feeds.items():
            ltp = self._nested_find_first(feed_payload, ("ltp", "lastPrice", "lp"))
            if ltp is None:
                continue
            volume = self._nested_find_first(feed_payload, ("vtt", "volume", "volTradedToday")) or 0
            oi = self._nested_find_first(feed_payload, ("oi", "open_interest", "openInterest")) or 0
            bid, ask = self._extract_upstox_bid_ask(feed_payload)
            greeks = self._extract_upstox_greeks(feed_payload)
            
            # Complex tick capture: (ts, symbol, price, volume, oi, delta, theta, bid, ask)
            self.tick_buffer.append((
                datetime.now(timezone.utc), 
                instrument_key, 
                ltp, 
                volume, 
                oi,
                greeks.get("delta"),
                greeks.get("theta"),
                bid, 
                ask
            ))

            if any(value is not None for value in greeks.values()):
                self.greeks_buffer.append(
                    (
                        datetime.now(timezone.utc),
                        instrument_key,
                        greeks["delta"],
                        greeks["theta"],
                        greeks["gamma"],
                        greeks["vega"],
                        greeks["iv"],
                    )
                )
                try:
                    asyncio.get_running_loop().create_task(
                        self.event_queue.put({"type": "greeks", "symbol": instrument_key, **greeks})
                    )
                except RuntimeError:
                    pass

    async def start(self, provider: str = "fyers", mode: str = "lite"):
        if self.is_running: return "Already running"
        self.provider_name = provider.lower()
        self.stream_mode = (mode or "lite").lower()
        self.adapter = get_adapter(self.provider_name)
        
        if not self.adapter.validate_token(): return "Token invalid"
        
        self.is_running = True
        asyncio.create_task(self.save_ticks_to_db())
        asyncio.create_task(self.save_greeks_to_db())
        
        if self.provider_name == "fyers":
            ws_token = f"{FYERS_CLIENT_ID}:{self.adapter._access_token}"
            use_litemode = self.stream_mode != "full"
            self.fyers_socket = FyersDataSocket(
                access_token=ws_token, log_path="", litemode=use_litemode,
                on_connect=self._on_open, on_message=self._on_fyers_message
            )
            threading.Thread(target=self.fyers_socket.connect, daemon=True).start()
        elif self.provider_name == "upstox":
            config = upstox_client.Configuration()
            config.access_token = self.adapter._access_token
            api_client = upstox_client.ApiClient(config)
            self.upstox_streamer = upstox_client.MarketDataStreamerV3(api_client=api_client)

            if self.stream_mode == "full":
                self._upstox_mode = upstox_client.MarketDataStreamerV3.Mode["FULL"]
            else:
                self._upstox_mode = upstox_client.MarketDataStreamerV3.Mode["LTPC"]

            self.upstox_streamer.on(upstox_client.MarketDataStreamerV3.Event["OPEN"], self._on_upstox_open)
            self.upstox_streamer.on(upstox_client.MarketDataStreamerV3.Event["MESSAGE"], self._on_upstox_message)
            self.upstox_streamer.on(upstox_client.MarketDataStreamerV3.Event["ERROR"], self._on_upstox_error)
            self.upstox_streamer.on(upstox_client.MarketDataStreamerV3.Event["CLOSE"], self._on_upstox_close)
            threading.Thread(target=self.upstox_streamer.connect, daemon=True).start()
        return "Started"

    def _on_open(self):
        self._ws_connected = True
        if self.symbols: self.fyers_socket.subscribe(self.symbols, data_type="SymbolUpdate")

    async def stop(self):
        self.is_running = False
        if self.fyers_socket: self.fyers_socket.close_connection()
        if self.upstox_streamer:
            try:
                self.upstox_streamer.disconnect()
            except Exception:
                pass
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
            elif self.provider_name == "upstox" and self.upstox_streamer and self._upstox_mode:
                mapped_symbols = [UPSTOX_UNDERLYING_KEYS.get(s, s) for s in added]
                self.upstox_streamer.subscribe(mapped_symbols, self._upstox_mode)
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
            elif self.provider_name == "upstox" and self.upstox_streamer:
                mapped_symbols = [UPSTOX_UNDERLYING_KEYS.get(s, s) for s in removed]
                self.upstox_streamer.unsubscribe(mapped_symbols)
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
    async def start(self, p, mode="lite"): return await self._recorders[p.lower()].start(p, mode)
    async def stop(self, p): return await self._recorders[p.lower()].stop()
    async def subscribe(self, p, s): return await self._recorders[p.lower()].subscribe(s)
    async def unsubscribe(self, p, s): return await self._recorders[p.lower()].unsubscribe(s)
    def get_status(self, p): return self._recorders[p.lower()].get_status()
    async def event_generator(self, p):
        async for e in self._recorders[p.lower()].event_generator(): yield e

recorder_manager = MultiProviderRecorderManager()
