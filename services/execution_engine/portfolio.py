import logging
from typing import Dict, Optional
from trading_core.models import Position, PositionSide, Fill, Side
from trading_core.events import bus, EventType, Event

logger = logging.getLogger("execution.portfolio")

class PortfolioManager:
    """Manages active positions, cash, and P&L tracking."""
    
    def __init__(self, initial_capital: float = 100000.0):
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.equity = initial_capital
        
        # Subscribe to Fills to update positions
        bus.subscribe(EventType.FILL, self._on_fill)

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    async def _on_fill(self, event: Event):
        # Handle FillEvent (I'll need to define FillEvent in events.py)
        # For now, let's assume it has a 'fill' property
        fill = getattr(event, 'fill', None)
        if not fill: return
        
        symbol = fill.symbol
        side = fill.side
        qty = fill.quantity
        price = fill.price
        
        logger.info(f"Updating portfolio with fill: {side} {qty} {symbol} @ {price}")
        
        if symbol not in self.positions:
            pos_side = PositionSide.LONG if side == Side.BUY else PositionSide.SHORT
            self.positions[symbol] = Position(symbol=symbol, side=pos_side, quantity=qty, avg_price=price)
        else:
            # Simple position averaging logic
            pos = self.positions[symbol]
            if (pos.side == PositionSide.LONG and side == Side.BUY) or \
               (pos.side == PositionSide.SHORT and side == Side.SELL):
                # Add to existing position
                total_qty = pos.quantity + qty
                pos.avg_price = ((pos.avg_price * pos.quantity) + (price * qty)) / total_qty
                pos.quantity = total_qty
            else:
                # Close or reverse position
                if pos.quantity > qty:
                    pos.quantity -= qty
                elif pos.quantity == qty:
                    del self.positions[symbol]
                else:
                    # Reversed
                    rem_qty = qty - pos.quantity
                    pos.side = PositionSide.LONG if side == Side.BUY else PositionSide.SHORT
                    pos.quantity = rem_qty
                    pos.avg_price = price
        
        # Update cash/equity (Simplified)
        cost = qty * price
        if side == Side.BUY: self.cash -= cost
        else: self.cash += cost
