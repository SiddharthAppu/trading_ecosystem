import asyncio
import logging
from datetime import datetime
from trading_core.events import bus, EventType, Tick, TickEvent
from trading_core.strategies import Strategy, StrategyContext
from services.execution_engine.portfolio import PortfolioManager
from services.execution_engine.executor import PaperExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("execution.main")

class ExecutionEngine:
    """The central orchestrator for a trading session."""
    
    def __init__(self):
        self.portfolio = PortfolioManager(initial_capital=100000)
        self.executor = PaperExecutor()
        self.strategy = None

    async def load_strategy(self, strategy_class, params):
        ctx = StrategyContext(bus, params, strategy_name=strategy_class.__name__)
        ctx.link_portfolio(self.portfolio)
        self.strategy = strategy_class(ctx)
        self.strategy.on_init()
        logger.info(f"Strategy {strategy_class.__name__} loaded.")

    async def start(self):
        logger.info("Execution Engine Started.")
        self.strategy.on_start()
        
        # In a real scenario, this would connect to a data feed
        # For now, let's simulate a few ticks to verify the engine
        # (This is where Step 4 will come in: connecting to Data Collector or Replay)
        
        symbol = "NIFTY26MAR24500CE"
        logger.info(f"Simulating market data for {symbol}...")
        
        for price in [100.0, 105.0, 110.0, 95.0, 102.0]:
            tick = Tick(symbol=symbol, price=price, timestamp=datetime.now(), volume=0)
            await bus.publish(TickEvent(tick=tick))
            await asyncio.sleep(0.5)

        self.strategy.on_stop()
        logger.info("Execution Engine Stopped.")

# --- Demo Strategy ---
class SimpleScalper(Strategy):
    async def on_bar(self, bar): pass
    
    async def on_tick(self, tick):
        pos = self.ctx.get_position(tick.symbol)
        if not pos and tick.price < 100:
            self.ctx.log(f"Buying {tick.symbol} at {tick.price}")
            await self.ctx.buy(tick.symbol, 50)
        elif pos and tick.price > 105:
            self.ctx.log(f"Closing {tick.symbol} at {tick.price}")
            await self.ctx.sell(tick.symbol, 50)

if __name__ == "__main__":
    engine = ExecutionEngine()
    asyncio.run(engine.load_strategy(SimpleScalper, {}))
    asyncio.run(engine.start())
