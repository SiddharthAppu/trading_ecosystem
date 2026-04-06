import logging
from typing import Dict, List
from trading_core.models import Order, OrderStatus, Fill, Side
from trading_core.events import bus, EventType, Event, OrderEvent

logger = logging.getLogger("execution.executor")

class PaperExecutor:
    """Simulated order executor for paper trading and backtesting."""
    
    def __init__(self, initial_capital: float = 100000.0):
        self.orders: Dict[str, Order] = {}
        # Subscribe to OrderEvents from strategies
        bus.subscribe(EventType.ORDER, self._on_order)
        bus.subscribe(EventType.TICK, self._on_tick)

    async def _on_order(self, event: OrderEvent):
        # Handle OrderEvent (I'll need to update events.py to define OrderEvent accurately)
        order = getattr(event, 'order', None)
        if not order: return
        
        logger.info(f"Order SUBMITTED: {order.side} {order.quantity} {order.symbol} @ {order.price or 'MARKET'}")
        self.orders[order.order_id] = order
        order.status = OrderStatus.SUBMITTED

    async def _on_tick(self, event: Event):
        # Simulate fill for Market Orders on next tick
        tick = getattr(event, 'tick', None)
        if not tick: return
        
        for order_id, order in list(self.orders.items()):
            if order.status == OrderStatus.SUBMITTED:
                # Market order or Price match
                if order.price is None or \
                   (order.side == Side.BUY and tick.price <= order.price) or \
                   (order.side == Side.SELL and tick.price >= order.price):
                    
                    fill = Fill(order_id=order.order_id, symbol=order.symbol, side=order.side, 
                                quantity=order.quantity, price=tick.price)
                    order.status = OrderStatus.FILLED
                    logger.info(f"Order FILLED: {order_id} @ {tick.price}")
                    
                    from trading_core.events import Event
                    fill_event = Event(event_type=EventType.FILL)
                    setattr(fill_event, 'fill', fill)
                    await bus.publish(fill_event)
                    
                    del self.orders[order_id]
