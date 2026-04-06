import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from typing import Optional

class Side(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

class PositionSide(str, enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"

class OrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"

class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

@dataclass(frozen=True)
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    timeframe: str = "1m"

@dataclass(frozen=True)
class Tick:
    symbol: str
    timestamp: datetime
    price: float
    volume: int
    side: Optional[Side] = None

@dataclass
class Order:
    symbol: str
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    order_id: str = field(default_factory=lambda: f"ord_{uuid.uuid4().hex[:8]}")
    created_at: datetime = field(default_factory=datetime.now)

@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    side: Side
    price: float
    quantity: int
    filled_at: datetime = field(default_factory=datetime.now)

@dataclass
class Position:
    symbol: str
    side: PositionSide
    quantity: int
    avg_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

@dataclass(frozen=True)
class ClosedTrade:
    trade_id: str
    symbol: str
    side: PositionSide
    entry_price: float
    exit_price: float
    quantity: int
    entry_time: datetime
    exit_time: datetime
    pnl: float
