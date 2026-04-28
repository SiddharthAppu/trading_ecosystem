from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional
from trading_core.models import Position, PositionSide, Side

@dataclass
class PortfolioManager:
    initial_capital: float
    positions: Dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    
    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def update_position(self, symbol: str, quantity: int, price: float, side: Side):
        if symbol not in self.positions:
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=0,
                avg_price=0.0,
                side=PositionSide.LONG if side == Side.BUY else PositionSide.SHORT
            )
        
        pos = self.positions[symbol]
        
        if (pos.side == PositionSide.LONG and side == Side.BUY) or \
           (pos.side == PositionSide.SHORT and side == Side.SELL):
            # Increasing position
            total_cost = (pos.avg_price * pos.quantity) + (price * quantity)
            pos.quantity += quantity
            pos.avg_price = total_cost / pos.quantity if pos.quantity != 0 else 0.0
        else:
            # Decreasing position or flipping
            if quantity <= pos.quantity:
                # Partial or full close
                pnl = (price - pos.avg_price) * quantity if pos.side == PositionSide.LONG else (pos.avg_price - price) * quantity
                self.realized_pnl += pnl
                pos.quantity -= quantity
                if pos.quantity == 0:
                    del self.positions[symbol]
            else:
                # Flipping side
                remaining_qty = quantity - pos.quantity
                pnl = (price - pos.avg_price) * pos.quantity if pos.side == PositionSide.LONG else (pos.avg_price - price) * pos.quantity
                self.realized_pnl += pnl
                
                pos.quantity = remaining_qty
                pos.avg_price = price
                pos.side = PositionSide.LONG if side == Side.BUY else PositionSide.SHORT
    
    def get_total_pnl(self, current_prices: Dict[str, float]) -> float:
        unrealized = 0.0
        for symbol, pos in self.positions.items():
            price = current_prices.get(symbol, pos.avg_price)
            if pos.side == PositionSide.LONG:
                unrealized += (price - pos.avg_price) * pos.quantity
            else:
                unrealized += (pos.avg_price - price) * pos.quantity
        return self.realized_pnl + unrealized
