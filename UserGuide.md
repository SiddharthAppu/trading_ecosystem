# 📖 Unified Trading Ecosystem - User Guide

This guide provides basic instructions on how to use and navigate the unified trading platform.

## 🏁 Getting Started
1.  **Dependencies**: Ensure Python 3.9+ and Node.js 18+ are installed.
2.  **Configuration**: Modify `config/.env` with your database and API credentials.
3.  **Startup**: Run `.\start_platform.bat` at the root of the project. This will open four terminal windows:
    - **DATA COLLECTOR**: Market connectivity and live data recording.
    - **REPLAY ENGINE**: Historical playback server.
    - **EXECUTION ENGINE**: Strategy orchestration.
    - **MAIN DASHBOARD**: Historical Dashboard (Next.js) on [http://localhost:3000](http://localhost:3000).

## 🧭 Platform Navigation
The platform consists of several internal apps and services:

### 📊 Historical Dashboard ([http://localhost:3000](http://localhost:3000))
- **Live Data View**: View real-time ticks and OHLC data during market hours.
- **Backtesting/Replay**: Start a replay of historical data for any selected date and instrument.
- **Session Replay UI**: A two-column interface for reviewing trading sessions with screenshots.

### 🔨 Strategy Forge ([http://localhost:3001](http://localhost:3001) - TBD)
- **Strategy Builder**: A visual tool to define rules for entries and exits.
- **Strategy Execution UI**: Monitor live performance, PnL, and open positions.

### 📶 Data Services
- **Data Collector**: API accessible at `http://localhost:8080`.
- **Replay WebSocket**: WebSocket communication on `ws://localhost:8765`.

## 💼 Core Concepts
### 🌍 The Trading Core
The `packages/trading_core` contains all shared logic:
- **Models**: Unified Tick, Bar, Candle, and Order data models.
- **Analytics**: Indicators (SMA, RSI, etc.) and risk management rules.
- **Events**: An asynchronous event-driven system to communicate between services.

### 🧩 Strategies
To add a new strategy:
1.  Navigate to `services/execution_engine/strategies/`.
2.  Create a new `.py` file inheriting from `trading_core.strategies.Strategy`.
3.  Implement `on_tick(self, event)` and `on_bar(self, event)`.

## 🛠 Troubleshooting
- **Port Conflict**: If port 3000 or 8080 is in use, modify the `.env` or application settings.
- **Database Error**: Ensure PostgreSQL/TimescaleDB is running and accessible from your network.
- **API Authentication**: Check `config/auth/` for valid Fyers/Upstox access tokens.

---
*Maintained by: Antigravity AI*
