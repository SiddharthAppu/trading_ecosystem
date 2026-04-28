import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from trading_core.models import Order, Fill, Side, OrderStatus
from trading_core.events import OrderEvent, FillEvent, bus, EventType
from trading_core.providers.base import BrokerAdapter

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
        logger.info(f"Paper executing {order.side} {order.quantity} {order.symbol}")
        
        # Simulate a fill
        fill = Fill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.price or 0.0, # Strategy should provide price or engine will fill it
            filled_at=datetime.now(timezone.utc)
        )
        
        order.status = OrderStatus.FILLED
        await bus.publish(FillEvent(fill=fill))

class LiveExecutor(BaseExecutor):
    """Executes orders on a real broker using an adapter."""
    def __init__(self, adapter: BrokerAdapter):
        super().__init__()
        self.adapter = adapter

    async def execute_order(self, order: Order):
        logger.info(f"Live executing {order.side} {order.quantity} {order.symbol} on {self.adapter.provider_name}")
        
        try:
            # Place order on broker
            broker_order_id = self.adapter.place_order(
                symbol=order.symbol,
                side=order.side.value,
                quantity=order.quantity,
                order_type="MARKET", # Default to market for now
                price=order.price,
                tag=order.tag
            )
            
            order.order_id = broker_order_id # Update with real ID if possible
            order.status = OrderStatus.PLACED
            
            # Note: In a real system, we'd wait for a WebSocket execution report.
            # For Astra lightweight, we'll poll or assume fill for Market orders 
            # if the broker API doesn't provide an instant status.
            # But here we'll just log it. The FillEvent should ideally come from 
            # a separate Poller or WebSocket listener in StrategyRuntime.
            
            logger.info(f"Order placed on {self.adapter.provider_name}: {broker_order_id}")
            
        except Exception as e:
            logger.error(f"Live execution failed: {e}")
            order.status = OrderStatus.REJECTED
            # Optionally publish a rejection event
