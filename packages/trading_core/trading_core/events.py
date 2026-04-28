import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Callable, Coroutine, Dict, List
from collections import defaultdict

# --- Event Types ---
class EventType(str, enum.Enum):
    BAR = "BAR"
    TICK = "TICK"
    SIGNAL = "SIGNAL"
    ORDER = "ORDER"
    FILL = "FILL"
    POSITION = "POSITION"
    ERROR = "ERROR"
    SESSION_START = "SESSION_START"
    SESSION_END = "SESSION_END"

from trading_core.models import Tick, Bar, Order, Side, Position, OrderStatus, Fill

# --- Events ---
@dataclass(frozen=True, kw_only=True)
class Event:
    event_type: EventType
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass(frozen=True, kw_only=True)
class TickEvent(Event):
    tick: Tick
    event_type: EventType = field(default=EventType.TICK, init=False)

@dataclass(frozen=True, kw_only=True)
class BarEvent(Event):
    bar: Bar
    event_type: EventType = field(default=EventType.BAR, init=False)

@dataclass(frozen=True, kw_only=True)
class OrderEvent(Event):
    order: Order
    action: str = "SUBMITTED" # SUBMITTED | FILLED | CANCELLED | REJECTED
    event_type: EventType = field(default=EventType.ORDER, init=False)

@dataclass(frozen=True, kw_only=True)
class SignalEvent(Event):
    symbol: str
    indicator: str
    value: Any
    threshold: Any
    action: str
    basket_id: str = "none"
    event_type: EventType = field(default=EventType.SIGNAL, init=False)

@dataclass(frozen=True, kw_only=True)
class FillEvent(Event):
    fill: Fill
    event_type: EventType = field(default=EventType.FILL, init=False)

# --- Event Bus ---
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]

class EventBus:
    """Centralized Async Event Bus for all services."""
    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: EventHandler):
        self._handlers[event_type].append(handler)

    async def publish(self, event: Event):
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                print(f"EventBus Error in {handler}: {e}")

# Global singleton
bus = EventBus()
