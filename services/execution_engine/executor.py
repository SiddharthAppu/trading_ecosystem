import logging
from typing import Dict
from trading_core.models import Order, OrderStatus, Fill, Side
from trading_core.events import bus, EventType, TickEvent, OrderEvent, FillEvent

logger = logging.getLogger("execution.executor")

class PaperExecutor:
    """Simulated order executor for paper trading and backtesting."""
    
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.orders: Dict[str, Order] = {}
        # Subscribe to OrderEvents from strategies
        bus.subscribe(EventType.ORDER, self._on_order)
        bus.subscribe(EventType.TICK, self._on_tick)

    async def _on_order(self, event: OrderEvent):
        order = event.order
        
        logger.info(
            "Order SUBMITTED: %s %s %s @ %s",
            order.side,
            order.quantity,
            order.symbol,
            order.price or "MARKET",
        )
        self.orders[order.order_id] = order
        order.status = OrderStatus.SUBMITTED

    async def _on_tick(self, event: TickEvent):
        tick = event.tick
        
        for order_id, order in list(self.orders.items()):
            if order.status == OrderStatus.SUBMITTED and order.symbol == tick.symbol:
                # Market order or Price match
                if order.price is None or \
                   (order.side == Side.BUY and tick.price <= order.price) or \
                   (order.side == Side.SELL and tick.price >= order.price):
                    
                    fill = Fill(order_id=order.order_id, symbol=order.symbol, side=order.side, 
                                quantity=order.quantity, price=tick.price)
                    order.status = OrderStatus.FILLED
                    logger.info("Order FILLED: %s @ %s", order_id, tick.price)

                    await bus.publish(FillEvent(fill=fill))
                    
                    del self.orders[order_id]
