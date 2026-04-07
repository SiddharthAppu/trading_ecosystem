# 🧠 Trading Ecosystem Project Memory

This file serves as the permanent brain of the `trading_ecosystem` monorepo. It explicitly tracks vital architecture constraints, bug-resolutions, and rigid design logic to prevent regressions during future development.

## 🏗️ Architecture & Core Structure
- **Monorepo Design**: The project centralizes logic in `packages/trading_core` (adapters, db schemas, abstractions), dividing runtime components into `services/` (backend logic) and `apps/` (frontend Dashboards). 
- **Standalone Scripts**: Orchestrator tasks (like `quick_download.py`, `quick_live_recorder.py`) sit in `scripts/`. They interact safely with the Core or communicate via HTTP to running services.

## 🗄️ Database Constraints (TimescaleDB)
- **Engine**: Dockerized TimescaleDB (`localhost:5432/trading_db`) mapped to `$ROOT/db_data`.
- **Primary Keys & Upserts**: All hyper-tables MUST feature a `UNIQUE(time, symbol)` index. We strictly enforce `ON CONFLICT DO NOTHING` during bulk inserts.
- **Batched Persistence**: Mass downloads (500k+ rows) must insert via batches (e.g. 1000 items/batch). Injecting the entire payload locks the instance and orchestrates fatal deadlocks across asynchronous pipelines.
- **Column Naming Rule**: NEVER use raw `calculated_` prefixes on analytical data schemas. All generated outputs must rigidly utilize the **`calc_`** prefix (e.g. `calc_implied_volatility`, `calc_delta`).

## 📡 API Providers: Quirks & Rules
### 1. Fyers Adapter
- **Paging Limits**: Historical downloaded chunks MUST not exceed **90 days**.
- **Option Symbol Engine**: `get_option_chain_symbols()` MUST rigorously reformat standard ISO dates (`YYYY-MM-DD`) into Fyers' unique Hex `YYM_CODE_DD` structures (e.g. `26413`) otherwise the WebSockets will silently ignore subscription packets.
- **Live Stream Tracking**: Extracts deeper orderbook data (`volume`, `bid`, `ask`) directly from the `SymbolUpdate` streams using `.get('v')`, `.get('bp1')`, etc. 

### 2. Upstox Adapter
- **Paging Limits**: Substantially stricter. Historical chunks MUST NOT exceed **30 days**.
- **Historical Gaps**: Upstox restricts 1-minute historical data access beyond ~1-2 years. The downloader is coded explicitly to swallow `Invalid Date Range` exceptions on the first chunk rather than fatally crashing the loop.

## 🔌 Service Runtimes & Singletons (Data Collector API)
- The Data Collector backend boots into memory via `start_platform.bat`.
- **Hot-Reloading Rule**: By default, `FyersAdapter` and `UpstoxAdapter` bind access tokens as continuous memory singletons. To prevent desync with external scripts (`verify_auth.py`), `validate_token()` explicitly runs `self._load_token()` to securely "hot-reload" updated keys dynamically from disk.

---
*(Auto-updated sequentially by the Agent to enforce continuity)*
