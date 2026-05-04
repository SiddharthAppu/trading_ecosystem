import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict

from trading_core.models import Order, Fill, OrderStatus
from trading_core.events import OrderEvent, FillEvent, bus
from trading_core.providers.base import BrokerAdapter

from services.strategy_runtime.time_utils import now_ist

logger = logging.getLogger("astra.executor")

class BaseExecutor(ABC):
    def __init__(self):
        self.orders: Dict[str, Order] = {}

    @abstractmethod
    async def execute_order(self, order: Order):
        pass

    async def handle_order_event(self, event: OrderEvent):
        if event.action == "SUBMITTED":
            await self.execute_order(event.order)

class PaperExecutor(BaseExecutor):
    """Simulates instant execution at the requested or latest price."""
    def __init__(self, initial_capital: float):
        super().__init__()
        self.capital = initial_capital

    async def execute_order(self, order: Order):
        logger.info("Paper executing %s %s %s", order.side, order.quantity, order.symbol)

        # Simulate a fill
        fill = Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.price or 0.0,
            filled_at=order.created_at if order.created_at else now_ist(),
        )

        order.status = OrderStatus.FILLED
        await bus.publish(FillEvent(fill=fill))

class LiveExecutor(BaseExecutor):
    """Executes orders on a real broker using an adapter."""
    def __init__(self, adapter: BrokerAdapter):
        super().__init__()
        self.adapter = adapter

    async def execute_order(self, order: Order):
        logger.info(
            "Live executing %s %s %s on %s",
            order.side,
            order.quantity,
            order.symbol,
            self.adapter.provider_name,
        )

        loop = asyncio.get_event_loop()
        try:
            # Place order on broker (sync call, run in thread to avoid blocking event loop)
            broker_order_id = await loop.run_in_executor(
                None,
                lambda: self.adapter.place_order(
                    symbol=order.symbol,
                    side=order.side.value,
                    quantity=order.quantity,
                    order_type="MARKET",
                    price=order.price,
                    tag=order.tag,
                ),
            )

            order.order_id = broker_order_id
            order.status = OrderStatus.SUBMITTED
            logger.info("Order placed on %s: broker_order_id=%s", self.adapter.provider_name, broker_order_id)

            # Poll for fill confirmation.  MARKET orders on Zerodha typically
            # fill within 1–2 seconds during market hours.
            fill = await self._poll_for_fill(order, broker_order_id, loop)
            if fill is not None:
                order.status = OrderStatus.FILLED
                await bus.publish(FillEvent(fill=fill))
            else:
                logger.warning(
                    "Fill confirmation timed out for broker_order_id=%s; order left as SUBMITTED",
                    broker_order_id,
                )

        except Exception as exc:
            logger.error("Live execution failed: %s", exc)
            order.status = OrderStatus.REJECTED

    async def _poll_for_fill(
        self,
        order: Order,
        broker_order_id: str,
        loop: asyncio.AbstractEventLoop,
        initial_delay: float = 2.0,
        retry_delay: float = 1.5,
        max_retries: int = 6,
    ):
        """Poll broker for order status until COMPLETE or max_retries exhausted.

        Returns a Fill on success, or None on timeout/rejection.
        """
        await asyncio.sleep(initial_delay)

        for attempt in range(1, max_retries + 1):
            try:
                broker_status = await loop.run_in_executor(
                    None,
                    lambda: self.adapter.get_order_status(broker_order_id),
                )
            except Exception as exc:
                logger.warning("get_order_status attempt %d failed: %s", attempt, exc)
                await asyncio.sleep(retry_delay)
                continue

            if broker_status is None:
                logger.warning("Order %s not found in broker order book (attempt %d)", broker_order_id, attempt)
                await asyncio.sleep(retry_delay)
                continue

            status = str(broker_status.get("status", "")).upper()
            logger.info("Poll attempt %d: broker_order_id=%s status=%s", attempt, broker_order_id, status)

            if status == "COMPLETE":
                avg_price = float(broker_status.get("average_price") or order.price or 0.0)
                filled_qty = int(broker_status.get("filled_quantity") or order.quantity)
                filled_at_raw = broker_status.get("exchange_update_timestamp") or broker_status.get("order_timestamp")
                from services.strategy_runtime.time_utils import parse_iso_to_ist
                filled_at = parse_iso_to_ist(str(filled_at_raw)) if filled_at_raw else now_ist()
                return Fill(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=filled_qty,
                    price=avg_price,
                    filled_at=filled_at,
                )

            if status in ("REJECTED", "CANCELLED"):
                logger.error(
                    "Order %s %s by broker: %s",
                    broker_order_id,
                    status,
                    broker_status.get("status_message", ""),
                )
                order.status = OrderStatus.REJECTED
                return None

            # Still OPEN/TRIGGER PENDING — wait and retry
            await asyncio.sleep(retry_delay)

        return None
