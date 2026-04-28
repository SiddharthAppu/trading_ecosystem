from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from trading_core.models import Bar, Tick, Order, Position, Fill, Side, OrderType, PositionSide
from trading_core.events import EventBus

class StrategyContext:
    """Interface provided to every strategy to interact with the platform."""
    
    def __init__(
        self,
        event_bus: EventBus,
        params: Dict[str, Any],
        strategy_name: str = ""
    ):
        self.bus = event_bus
        self.params = params
        self.name = strategy_name
        self.portfolio = None # Will be linked by the engine

    def link_portfolio(self, portfolio):
        self.portfolio = portfolio

    def get_position(self, symbol: str) -> Optional[Position]:
        if not self.portfolio: return None
        return self.portfolio.get_position(symbol)

    def log(self, message: str):
        print(f"[{self.name}] {message}")

    def get_param(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)

    async def log_signal(self, symbol: str, indicator: str, value: Any, threshold: Any, action: str, basket_id: str = "none"):
        from trading_core.events import SignalEvent
        await self.bus.publish(SignalEvent(
            symbol=symbol,
            indicator=indicator,
            value=value,
            threshold=threshold,
            action=action,
            basket_id=basket_id
        ))

    async def buy(self, symbol: str, qty: int, price: Optional[float] = None, tag: str = "", basket_id: str = "none"):
        order = Order(symbol=symbol, side=Side.BUY, quantity=qty, price=price, tag=tag)
        # Add basket_id to order object
        setattr(order, "basket_id", basket_id)
        from trading_core.events import OrderEvent
        await self.bus.publish(OrderEvent(order=order, action="SUBMITTED"))
        return order.order_id

    async def sell(self, symbol: str, qty: int, price: Optional[float] = None, tag: str = "", basket_id: str = "none"):
        order = Order(symbol=symbol, side=Side.SELL, quantity=qty, price=price, tag=tag)
        # Add basket_id to order object
        setattr(order, "basket_id", basket_id)
        from trading_core.events import OrderEvent
        await self.bus.publish(OrderEvent(order=order, action="SUBMITTED"))
        return order.order_id

class Strategy(ABC):
    """Abstract Base Class for all trading strategies."""
    
    def __init__(self, context: StrategyContext):
        self.ctx = context

    def on_init(self): pass
    def on_start(self): pass
    def on_stop(self): pass

    @abstractmethod
    async def on_bar(self, bar: Bar): ...
    
    async def on_tick(self, tick: Tick): pass
    async def on_fill(self, fill: Fill): pass
