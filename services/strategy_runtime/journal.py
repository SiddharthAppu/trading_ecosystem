import json
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("astra.journal")

class JournalManager:
    """
    Asynchronously logs trading events to a JSONL (JSON Lines) file.
    This is the primary source of truth for Astra in Zero-DB mode.
    """
    def __init__(self, journal_path: str, strategy_name: str = "AstraDefault", timeframe: str = "1m"):
        self.path = Path(journal_path)
        self.strategy_name = strategy_name
        self.timeframe = timeframe
        self._lock = asyncio.Lock()
        self._initialized = False

    def _ensure_dir(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def log_event(self, event_type: str, symbol: str, payload: Dict[str, Any], basket_id: str = "none"):
        """Append an event to the journal file with full context."""
        if not self._initialized:
            self._ensure_dir()
            self._initialized = True

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "strategy": self.strategy_name,
            "timeframe": self.timeframe,
            "symbol": symbol,
            "basket_id": basket_id,
            "data": payload
        }

        async with self._lock:
            try:
                await asyncio.to_thread(self._append_to_file, entry)
            except Exception as e:
                logger.error(f"Failed to write to journal: {e}")

    def _append_to_file(self, entry: Dict[str, Any]):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    async def log_indicator_signal(self, symbol: str, indicator: str, value: Any, threshold: Any, action: str, basket_id: str = "none"):
        await self.log_event("INDICATOR_PASSED", symbol, {
            "indicator": indicator,
            "value": value,
            "threshold": threshold,
            "action": action
        }, basket_id=basket_id)

    async def log_order(self, symbol: str, order_data: Dict[str, Any], basket_id: str = "none"):
        await self.log_event("ORDER_PLACED", symbol, order_data, basket_id=basket_id)

    async def log_fill(self, symbol: str, fill_data: Dict[str, Any], basket_id: str = "none"):
        await self.log_event("ORDER_FILL", symbol, fill_data, basket_id=basket_id)

    def recover_state(self) -> list[Dict[str, Any]]:
        """
        Read the journal file and return all ORDER_FILL entries in chronological order.
        Returns an empty list if the journal does not exist or is unreadable.
        Each returned dict has keys: symbol, side, quantity, price, order_id, filled_at.
        """
        if not self.path.exists():
            return []
        fills: list[Dict[str, Any]] = []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for line_num, raw_line in enumerate(fh, start=1):
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Journal line %d is not valid JSON — skipped", line_num)
                        continue
                    if entry.get("event") != "ORDER_FILL":
                        continue
                    data = entry.get("data", {})
                    fills.append(
                        {
                            "symbol": entry.get("symbol", ""),
                            "side": data.get("side", ""),
                            "quantity": int(data.get("quantity", 0)),
                            "price": float(data.get("price", 0.0)),
                            "order_id": data.get("order_id", ""),
                            "filled_at": data.get("filled_at", entry.get("ts", "")),
                        }
                    )
        except OSError as exc:
            logger.error("Could not read journal for recovery: %s", exc)
        return fills
