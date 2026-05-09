from __future__ import annotations

import math

from trading_core.strategies import Strategy


class StrategyImpl(Strategy):
    async def on_bar(self, _bar):
        return None

    async def evaluate_snapshot(self, snapshot):
        lot_quantity = int(self.ctx.get_param("lot_quantity", 1))
        lot_size = int(self.ctx.get_param("lot_size", 1))
        capital_model = str(self.ctx.get_param("capital_model", "non_compounding")).strip().lower()
        initial_capital = float(self.ctx.get_param("initial_capital", 100000.0))

        effective_lots = max(1, lot_quantity)
        if capital_model == "compounding" and self.ctx.portfolio is not None:
            capital_available = initial_capital + float(self.ctx.portfolio.get_total_pnl({}))
            one_lot_cost = float(snapshot.bar.close) * max(1, lot_size)
            if one_lot_cost > 0:
                effective_lots = max(1, math.floor(capital_available / one_lot_cost))

        effective_units = max(1, effective_lots * max(1, lot_size))

        ema_value = snapshot.indicators.get("ema_20")
        sma_value = snapshot.indicators.get("sma_20")
        if ema_value is None or sma_value is None:
            return

        position = self.ctx.get_position(snapshot.symbol)
        if position is None and snapshot.bar.close > ema_value and ema_value > sma_value:
            await self.ctx.buy(snapshot.symbol, effective_units, tag="ema_cross_entry")
            return

        if position and snapshot.bar.close < ema_value:
            await self.ctx.sell(snapshot.symbol, position.quantity, tag="ema_cross_exit")
