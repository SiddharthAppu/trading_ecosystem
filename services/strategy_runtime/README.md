Strategy runtime is a separate backend service for signal generation and paper execution.

Strategy scaffold (folder per strategy):

- services/strategy_runtime/strategies/<strategy_name>/strategy.py with class StrategyImpl
- services/strategy_runtime/strategies/<strategy_name>/config.py optional get_default_params()
- services/strategy_runtime/strategies/<strategy_name>/strategy.env.example optional strategy-local env hints

Current built-in example:

- services/strategy_runtime/strategies/ema_cross/strategy.py

Built-in ema_cross status:

- Yes, ema_cross is already coded and runnable.
- Entry logic: buy when close > ema_20 and ema_20 > sma_20 and there is no open position.
- Exit logic: sell when price closes back below ema_20.
- Runtime risk layer still applies stop loss and trailing stop outside the strategy logic.

Environment variables:
- STRATEGY_RUNTIME_FEED_SOURCE: broker or replay_ws
- STRATEGY_RUNTIME_PROVIDER: fyers or upstox
- STRATEGY_RUNTIME_SYMBOL: broker symbol or instrument key
- STRATEGY_RUNTIME_TIMEFRAME: 1m, 5m, 10m
- STRATEGY_RUNTIME_POLL_SECONDS: polling interval for historical-bar refresh
- STRATEGY_RUNTIME_STRATEGY: currently ema_cross
- STRATEGY_RUNTIME_STRATEGY_CLASS: optional plugin class path, for example my_strategies.breakout.BreakoutStrategy
- STRATEGY_RUNTIME_QUANTITY: order quantity per entry
- STRATEGY_RUNTIME_MAX_POSITION_QTY: max total open quantity per symbol
- STRATEGY_RUNTIME_MAX_NOTIONAL: max notional exposure for a single entry
- STRATEGY_RUNTIME_STOP_LOSS_PCT: fixed stop percentage for open long positions
- STRATEGY_RUNTIME_TRAILING_STOP_PCT: trailing stop percentage for open long positions
- STRATEGY_RUNTIME_AUTOSTART: true or false for API server startup behavior
- STRATEGY_RUNTIME_REPLAY_WS_URL: replay websocket URL (default ws://localhost:8765)
- STRATEGY_RUNTIME_REPLAY_DATA_TYPE: market_ticks, ohlcv_1m, ohlcv_1min_from_ticks, options_ohlc
- STRATEGY_RUNTIME_REPLAY_SPEED: replay speed multiplier
- STRATEGY_RUNTIME_REPLAY_START_TIME and STRATEGY_RUNTIME_REPLAY_END_TIME: optional ISO window
- TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID: optional alerting

Run with:
python main.py

Run with monitor API (port 8090):
python server.py

API endpoints:
- GET /health
- GET /status
- GET /events?limit=100
- GET /runtime/config
- POST /runtime/start
- POST /runtime/stop
- POST /runtime/restart

Paper trade testing without live ticks (Replay Studio websocket):

1. Start replay websocket server:
	python services/replay_engine/main.py
2. Replay engine exposes:
	- WebSocket stream: ws://localhost:8765
	- HTTP load API: http://localhost:8766/replay/load
3. Configure runtime env:
	- STRATEGY_RUNTIME_FEED_SOURCE=replay_ws
	- STRATEGY_RUNTIME_REPLAY_WS_URL=ws://localhost:8765
	- STRATEGY_RUNTIME_REPLAY_DATA_TYPE=ohlcv_1m (or market_ticks)
	- STRATEGY_RUNTIME_SYMBOL=<symbol available in replay DB>
	- STRATEGY_RUNTIME_PROVIDER=fyers or upstox (schema selector)
4. Start runtime API:
	python services/strategy_runtime/server.py
5. Start Forge dashboard:
	cd apps/forge_dashboard
	set NEXT_PUBLIC_RUNTIME_API_URL=http://localhost:8090
	set NEXT_PUBLIC_API_URL=http://localhost:8000
	npm run dev
6. Open Forge Runtime page and start monitoring:
	http://localhost:3001/runtime

Single-command wrapper flow:

1. Edit config/strategy_runtime.ema_cross.paper_replay.env.
2. Start replay + runtime together:
	powershell -ExecutionPolicy Bypass -File scripts/start_strategy_runtime_paper_replay.ps1 -Strategy ema_cross -StartReplayEngine
3. Start Forge separately if you want the UI.

Telegram alerts:

1. Create a bot using BotFather and copy bot token.
2. Send at least one message to the bot from your Telegram account/group.
3. Resolve chat id via getUpdates.
4. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID before starting runtime.

Wrapper launcher with env file:

1. Create/edit a strategy-specific env file such as config/strategy_runtime.ema_cross.paper_replay.env.
2. Run script from repo root:
	powershell -ExecutionPolicy Bypass -File scripts/start_strategy_runtime_paper_replay.ps1 -StartReplayEngine

Optional custom env file path:
	powershell -ExecutionPolicy Bypass -File scripts/start_strategy_runtime_paper_replay.ps1 -EnvFile config/your_runtime.env -StartReplayEngine

Optional explicit strategy key (used for auto env resolution):
	powershell -ExecutionPolicy Bypass -File scripts/start_strategy_runtime_paper_replay.ps1 -Strategy ema_cross -StartReplayEngine

Cloud kit packaging guidance:

For a deployable cloud kit, include:
- services/strategy_runtime/** (including strategies/* folders)
- required shared modules from packages/trading_core/**
- required execution helpers used by runtime from services/execution_engine/**
- runtime env files and config/auth mount or secret integration

So yes, the full strategy_runtime folder should be copied with its strategy folders, plus required shared dependencies.