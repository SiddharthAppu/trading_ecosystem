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
- **Options Data Feed**: The historical expired candle API provides Open Interest (OI) at **index 6** of the candle array.
- **Historical Options Sync**: The `upstox_options_sync.py` script features a **cross-provider spot fallback**. If Upstox spot data (`ohlcv_1m`) is missing for a requested trade date (common for dates before 2023), it automatically queries `broker_fyers.ohlcv_1m` to resolve the ATM strike and proceed with the Upstox options download.
- **Upstox API Rate Limiting (Options Downloader)**: Explicitly enforced rules to survive their strict historical candle rate limits (~3/sec ceiling): 
  - **The 400ms Rule:** A hard `0.4s` sleep is injected after *every single* GET request.
  - **Ghost Limits:** Upstox silently throttles by returning `Status 200` but yielding an empty `{}` candle array. `upstox_historical.py` safely detects this, ignores it, and forces a 5s retry loop (up to 3 times) before giving up to maintain strict data integrity.
  - **Integrity Validation:** A newly integrated standalone tool (`services/data_collector/scripts/audit_upstox_options.py`) can be triggered post-download. It randomly selects stored database entries and fetches them live from the API to assert accurate DB reconstruction.

## 🔌 Service Runtimes & Singletons (Data Collector API)
- The Data Collector backend boots into memory via `start_platform.bat`.
- **Hot-Reloading Rule**: By default, `FyersAdapter` and `UpstoxAdapter` bind access tokens as continuous memory singletons. To prevent desync with external scripts (`verify_auth.py`), `validate_token()` explicitly runs `self._load_token()` to securely "hot-reload" updated keys dynamically from disk.

## 📊 Analytics & Diagnostics
- **Gap Detection Logic**: When calculating data gaps in periodic tables (OHLC, Greeks), we strictly filter for intra-day events (`time::date = prev_time::date`). This prevents the diagnostic dashboard from reporting the expected overnight gap (3:30 PM - 9:15 AM) as "Missing Minutes".

---
*(Auto-updated sequentially by the Agent to enforce continuity)*
