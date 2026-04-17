# 🌌 Unified Trading Ecosystem - Operations Guide

Welcome to your consolidated trading platform. This repository unifies **HistoricalDownlaod**, **OptionsStrategyTester**, and **StrategyForge** into a modular, provider-neutral system.

## 📁 System Architecture
```text
trading_ecosystem/
├── apps/
│   ├── historical_dashboard/  # Next.js - Historical data & Replay UI (Port 3000)
│   └── forge_dashboard/       # Next.js - Strategy Builder & Execution UI (Port 3001)
├── packages/
│   └── trading_core/          # Shared Logic (Symbols, Analytics, Models, Events)
├── services/
│   ├── data_collector/        # Market connectivity & Live Recording (Port 8080)
│   ├── replay_engine/         # Historical playback server (Port 8765)
│   └── execution_engine/      # Strategy orchestration & Portfolio manager
├── config/
│   ├── .env                   # Central Database & API credentials
│   └── auth/                  # Access tokens for Fyers & Upstox
└── start_platform.bat         # Single-click master startup script
```

## 🛠️ Developer Information

### Startup Presets
- `start_platform.bat all`: Full stack (DB + collector + replay + execution + UIs).
- `start_platform.bat replay-studio`: Replay-only stack (DB + replay engine + historical dashboard).
- `start_platform.bat collector+replay`: DB + collector + replay engine.
- `start_platform.bat collector`: DB + collector.
- `start_platform.bat replay`: DB + replay engine.

### Replay Studio Runtime Contract
- Historical Dashboard Replay Studio uses the replay engine endpoints directly:
	- WebSocket stream: `ws://localhost:8765`
	- Load API: `http://localhost:8766/replay/load`
- Replay Studio does not require the live data collector process unless you are also recording new market data.
- Startup launcher now waits for TimescaleDB health before starting dependent services.

### 🌍 Global Ports mapped
- **Historical UI**: `http://localhost:3000`
- **Data Collector API**: `http://localhost:8080`
- **Replay WebSocket**: `ws://localhost:8765`

### 🔄 The Event-Driven Heart
All services communicate via the **Asynchronous Event Bus** in `trading_core.events`. 
- **Publish**: `await bus.publish(TickEvent(tick=tick))`
- **Subscribe**: `bus.subscribe(EventType.TICK, self._on_tick)`

### 🧩 Plugin System (Strategies)
New strategies should be placed in `services/execution_engine/strategies/` and inherit from `trading_core.strategies.Strategy`. They automatically receive a `StrategyContext` with access to portfolio positions and order execution.

### ✅ Verification Steps
1.  Verify database connection in `config/.env`.
2.  Run `start_platform.bat replay-studio` for replay workflows, or `start_platform.bat all` for the full platform.
3.  Historical Dashboard should load on port `3000`.

---
*Consolidated by Antigravity AI - 2026-04-06*
