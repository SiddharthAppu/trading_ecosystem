# 🧠 Trading Ecosystem: Permanent Project Brain

This document is the absolute ground truth for the trading ecosystem architecture, logic, and environment constraints. It consolidates all previous directives, linting rules, and API behaviors so that you can safely clear your older constraints.

## 1. Options Strategy Logic & Trading Mechanics
- **Activation:** Always On
- **Precision:** Mathematical operations related to strike prices, premiums, and Greeks MUST rigorously use Python's `Decimal` class. Never use standard `float`.
- **Strategy Definition:** The active automation model focuses on an **Iron Condor**. Short strikes must mathematically be plotted strictly at exactly **2 standard deviations** from the asset's active spot price.
- **Delta & Greeks:** The core Black-Scholes calculus model is explicitly mapped and referenced inside `utils/greeks.py`.

## 2. API Providers & Data Integration
### Upstox Adapter
- **Paging Limits:** Upstox restricts downloaded chunks to **30-day limits** for smaller data intervals.
- **History Deprecation:** Upstox drops 1-minute historical data access beyond ~1-2 years. The system logic intentionally catches the `Invalid Date Range / UDAPI1148` error on the initial chunk and skips it, refusing to halt the remainder of the download.
- **Provider Neutrality:** The Upstox connection is abstracted behind the core `BrokerAdapter` interface so analytical tools interact identically with Upstox or Fyers.
- **Chain Downloads:** Historical Option Chain analysis operates via `quick_option_chain.py` hitting Upstox to verify symbols. If Upstox errors about a missing symbol in the chain down, do **not prevent process flow**. Log the missing strike dynamically into `error_log.csv` and systematically continue.

### Fyers Adapter
- **Websocket Logic:** Live market depth (Bid/Ask/Volume) is extracted rigorously via the LiteMode=False settings. 
- **Symbol Processing:** Fyers exclusively tracks option symbols in weekly chains using a Hex format: `YYM_CODE_DD` (e.g. `26413` substituting for `2026-04-13`). `YYYY-MM-DD` must always undergo Regex translation before Websocket subscription.

## 3. Database Integrity & Structure
- **Core:** TimescaleDB persistent instance mapped independently via `docker-compose.yml` to the ignored `db_data/` folder.
- **Primary Constraints:** All schema inserts specifically employ `UNIQUE(time, symbol)` to trigger UPSERTs (`ON CONFLICT DO NOTHING`).
- **Batching Locks:** Massive payloads (500k+ rows) must explicitly bulk execute in **1000-row chunks** to escape unrecoverable database deadlocks.
- **Analytical Overrides:** All generated tracking rows referencing metrics or greeks *must strictly* begin with the explicit **`calc_`** prefix (e.g., `calc_iv`, `calc_delta`).

## 4. Environment, Linting & Command Checks
- **Start Platform:** The `start_platform.bat` script is the unalienable entry point to universally bind backend providers and trigger TimescaleDB.
- **Python Linting:** Always run **`ruff check --fix`** on the specific terminal path manually after successfully writing or modifying any backend files inside `services/` or `packages/`.
- **Next.js Linting:** Strictly use **`node_modules\.bin\next lint`** inside the Next.js `apps/` UI environment to execute frontend checks. Note: `npx check` usage is strictly forbidden. 
- **Session Tokens:** Tokens are cached as memory singletons in FastAPI but MUST hot-reload via disk sync so CLI-auth commands natively sync universally.

---
*Note to Agent: Periodically review and refine this schema anytime a core piece of backend logic changes inside `trading_core`.*
