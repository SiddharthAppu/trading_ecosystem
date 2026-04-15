from __future__ import annotations

from trading_core.strategies import Strategy


class StrategyImpl(Strategy):
    async def on_bar(self, _bar):
        return None

    async def evaluate_snapshot(self, snapshot):
        ema_value = snapshot.indicators.get("ema_20")
        sma_value = snapshot.indicators.get("sma_20")
        if ema_value is None or sma_value is None:
            return

        position = self.ctx.get_position(snapshot.symbol)
        if position is None and snapshot.bar.close > ema_value and ema_value > sma_value:
            await self.ctx.buy(snapshot.symbol, self.ctx.get_param("quantity", 1), tag="ema_cross_entry")
            return

        if position and snapshot.bar.close < ema_value:
            await self.ctx.sell(snapshot.symbol, position.quantity, tag="ema_cross_exit")
