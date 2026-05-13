import json
import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Dict

from services.strategy_runtime.time_utils import now_ist, parse_iso_to_ist

logger = logging.getLogger("astra.journal")

class JournalManager:
    """
    Asynchronously logs trading events to a JSONL (JSON Lines) file.
    This is the primary source of truth for Astra in Zero-DB mode.
    """
    def __init__(
        self,
        journal_path: str,
        strategy_name: str = "AstraDefault",
        timeframe: str = "1m",
        capital_context_provider: Callable[[], Dict[str, Any]] | None = None,
    ):
        self.path = Path(journal_path)
        self.strategy_name = strategy_name
        self.timeframe = timeframe
        self._capital_context_provider = capital_context_provider
        self._lock = asyncio.Lock()
        self._initialized = False

    def _ensure_dir(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def log_event(
        self,
        event_type: str,
        symbol: str,
        payload: Dict[str, Any],
        basket_id: str = "none",
        event_ts: str | None = None,
        capital_context: Dict[str, Any] | None = None,
    ):
        """Append an event to the journal file with full context."""
        if not self._initialized:
            self._ensure_dir()
            self._initialized = True

        write_ts = now_ist().isoformat()
        resolved_event_ts = parse_iso_to_ist(event_ts) if event_ts else write_ts
        resolved_capital_context = capital_context
        if resolved_capital_context is None and self._capital_context_provider is not None:
            try:
                resolved_capital_context = self._capital_context_provider()
            except (TypeError, ValueError, AttributeError, RuntimeError):
                resolved_capital_context = None

        entry = {
            "ts": resolved_event_ts,
            "event_ts": resolved_event_ts,
            "logged_at": write_ts,
            "event": event_type,
            "strategy": self.strategy_name,
            "timeframe": self.timeframe,
            "symbol": symbol,
            "basket_id": basket_id,
            "data": payload
        }
        if resolved_capital_context is not None:
            entry["capital"] = resolved_capital_context

        async with self._lock:
            try:
                await asyncio.to_thread(self._append_to_file, entry)
            except OSError as exc:
                logger.error("Failed to write to journal: %s", exc)

    def _append_to_file(self, entry: Dict[str, Any]):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    async def log_run_header(
        self,
        symbol: str,
        strategy: str,
        timeframe: str,
        indicators: list[str],
        run_params: dict[str, Any],
        basket_id: str = "none",
        capital_context: Dict[str, Any] | None = None,
    ) -> None:
        """Write a RUNTIME_HEADER event as the first entry of a new run journal.
        Contains strategy configuration and parameters for backtracking."""
        await self.log_event(
            "RUNTIME_HEADER",
            symbol,
            {
                "strategy": strategy,
                "timeframe": timeframe,
                "indicators": indicators,
                **run_params,
            },
            basket_id=basket_id,
            capital_context=capital_context,
        )

    async def log_indicator_signal(
        self,
        symbol: str,
        indicator: str,
        value: Any,
        threshold: Any,
        action: str,
        basket_id: str = "none",
        capital_context: Dict[str, Any] | None = None,
    ):
        await self.log_event("INDICATOR_PASSED", symbol, {
            "indicator": indicator,
            "value": value,
            "threshold": threshold,
            "action": action
        }, basket_id=basket_id, capital_context=capital_context)

    async def log_entry_passed(
        self,
        symbol: str,
        entry_data: Dict[str, Any],
        basket_id: str = "none",
        event_ts: str | None = None,
        capital_context: Dict[str, Any] | None = None,
    ):
        """Log entry signal decision before order placement.
        Used for charting entry decisions on the underlying symbol.
        
        entry_data should contain:
        - price: underlying price at entry time
        - decision: "BULLISH" or "BEARISH"
        - target_price: target exit price
        - stop_price: stop-loss exit price
        - reason: optional reasoning string (e.g., "EMA > SMA + MACD > 0")
        """
        await self.log_event(
            "ENTRY_PASSED",
            symbol,
            entry_data,
            basket_id=basket_id,
            event_ts=event_ts,
            capital_context=capital_context,
        )

    async def log_order(
        self,
        symbol: str,
        order_data: Dict[str, Any],
        basket_id: str = "none",
        event_ts: str | None = None,
        capital_context: Dict[str, Any] | None = None,
    ):
        await self.log_event(
            "ORDER_PLACED",
            symbol,
            order_data,
            basket_id=basket_id,
            event_ts=event_ts,
            capital_context=capital_context,
        )

    async def log_fill(
        self,
        symbol: str,
        fill_data: Dict[str, Any],
        basket_id: str = "none",
        capital_context: Dict[str, Any] | None = None,
    ):
        await self.log_event(
            "ORDER_FILL",
            symbol,
            fill_data,
            basket_id=basket_id,
            event_ts=str(fill_data.get("filled_at", "")) or None,
            capital_context=capital_context,
        )

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
