# Astra: Low-Level Design (LLD)
**Version**: 1.0
**Target System**: Cloud-Native Strategy Executor

---

## 1. System Components & Class Diagram

### A. Core Foundation (`trading_core`)
*   **`BaseAdapter`**: Abstract base class defining the contract for all brokers (Fyers, Upstox).
    *   `get_positions()`: Used by Astra for "Self-Heal" state re-sync.
    *   `place_order(order)`: Standardized execution hook.
    *   `get_order_status(order_id)`, `get_orders()`: Used for live order supervision and recovery.
    *   `get_available_funds()`, `get_margin()`, `get_portfolio_status()`: Used for broker-side account health and runtime status APIs.
*   **`SignalEvent`**: Dataclass representing a strategy trigger.
    *   Fields: `symbol`, `indicator`, `value`, `threshold`, `action`, `basket_id`.
*   **`StrategyContext`**: The sandbox interface for algorithms.
    *   `log_signal(...)`: Proxies to `EventBus.publish(SignalEvent)`.
    *   `buy(...)`/`sell(...)`: Proxies to `EventBus.publish(OrderEvent)` with `basket_id` support.
*   **`Analytics Facade`**: A stable indicator API inside `trading_core.analytics`.
    *   Current state: In-house EMA, SMA, RSI, MACD functions.
    *   Planned state: Wrapper over a vetted indicator backend with parity tests against current outputs.

### B. The Engine (`strategy_runtime`)
*   **`StrategyRuntime`**: The main execution loop. Orchestrates data ingestion and strategy evaluation.
    *   Handles `EventType.SIGNAL` -> Dispatches to `JournalManager`.
    *   Handles `EventType.BAR` -> Dispatches to `Strategy.evaluate_snapshot`.
    *   Will expose broker-side positions, orders, funds, and margin via status APIs for operational visibility.
*   **`JournalManager`**: Thread-safe, asynchronous file writer.
    *   `_append_to_file(entry)`: Uses `asyncio.to_thread` to prevent blocking the trading loop during I/O.
    *   Format: JSON Lines (`.jsonl`) for atomic recovery and easy log parsing.
*   **`BrokerPollingBarFeed`**: In-memory data aggregator.
    *   Warms up by fetching the last `N` bars from the Broker API on startup (Zero-DB mode).
*   **`RuntimeSupervisor`**: Planned background loop for state reconciliation.
    *   Polls broker positions and order book every fixed interval.
    *   Detects drift between broker truth and in-memory state.
    *   Triggers alerting and optional compensating actions.

### C. The Collector (`data_collector`)
*   **`LiveTickRecorder`**: WebSocket lifecycle manager.
    *   Extracts `OI`, `Delta`, `Theta` from raw broker packets.
*   **`TickFileLogger`**: Dedicated high-speed file streaming engine.
    *   Groups ticks by symbol and appends to `ticks_{date}.csv`.

---

## 2. Sequence Diagrams

### A. Tick-to-Signal-to-Trade Flow
1.  **WebSocket** receives raw tick from Broker.
2.  **`LiveTickRecorder`** normalizes the tick + greeks.
3.  **`TickFileLogger`** writes the tick to CSV.
4.  **`StrategyRuntime`** picks up the data and pulses the **`Strategy`**.
5.  **`Strategy`** logic passes (e.g., RSI > 70).
6.  **`StrategyContext.log_signal()`** is called.
7.  **`JournalManager`** records the `INDICATOR_PASSED` event.
8.  **`StrategyContext.buy()`** is called with a `basket_id`.
9.  **`JournalManager`** records the `ORDER_PLACED` event.

### B. Restart Recovery Flow
1.  **`StrategyRuntime`** starts and opens `journal.jsonl`.
2.  **`JournalRecovery`** replays prior `ORDER_PLACED`, `ORDER_FILL`, and signal events.
3.  **Portfolio state** is reconstructed in memory.
4.  **BrokerAdapter.get_positions()` and `BrokerAdapter.get_orders()`** are queried.
5.  **RuntimeSupervisor** compares journal-derived state with broker truth.
6.  **Mismatch events** are written to the journal and sent to Telegram.

---

## 3. Data Schema Definitions

### A. Flat File Ticks (`.csv`)
Header: `timestamp,symbol,price,volume,oi,delta,theta,bid,ask`
*   **Format**: `isoformat()` timestamps (e.g., `2026-04-27T10:00:00.000Z`) to ensure compatibility with TimescaleDB.

### B. Execution Journal (`.jsonl`)
Every line is a valid JSON object.
*   **Common Context**: `strategy_name`, `timeframe`, `basket_id`, `symbol` are injected into every record.
*   **Recovery Requirement**: Order and fill records must preserve enough broker identifiers to rebuild pending state after restart.

### C. Broker Status Snapshot
Runtime status should expose a normalized broker snapshot:
*   `positions`
*   `orders`
*   `available_funds`
*   `margin`
*   `last_sync_time`

---

## 4. Indicator Engine Decision

### A. Current State
*   Technical indicators are computed by in-house functions inside `trading_core.analytics`.
*   Option greeks use `py_vollib` when available.

### B. Library Comparison
| Library | Strengths | Weaknesses | Astra Fit |
| :--- | :--- | :--- | :--- |
| **TA-Lib** | Mature, fast C-backed implementation, widely validated | Native dependency/install friction on Windows and CI | **Best choice for production core indicators if packaging is handled** |
| **pandas-ta** | Large indicator coverage, pandas-friendly API, pure Python | Heavier dependency surface, dataframe-centric, can be slower/noisier for runtime loops | Good for research, weaker for lean runtime |
| **stock-indicators** | Good correctness reputation, broad indicator set, Python wrapper over tested core | Less common in trading infra, extra dependency model, less ecosystem familiarity | Reasonable fallback candidate |
| **vectorbt / vectorbtpro** | Excellent research/backtesting workflows, vectorized analytics | Heavy stack, not ideal as a low-footprint live runtime dependency | Good research layer, not ideal runtime dependency |

### C. Recommended Direction
*   Keep `trading_core.analytics` as the only public indicator interface.
*   Add a backend abstraction under that facade.
*   Use **TA-Lib** as the preferred production backend for standard indicators.
*   Keep the current in-house implementations as a deterministic fallback and for parity testing.
*   Add comparison tests that validate TA-Lib outputs vs current outputs over representative market datasets before switching runtime defaults.
*   Integrate TA-Lib **before** production kit freeze, but **after** the analytics facade and parity harness exist. Do not couple the first TA-Lib rollout directly to strategy logic.
*   Current implementation status: the facade exists and can switch between `inhouse` and `talib` backends; TA-Lib remains optional until parity and packaging validation are complete.

---

## 5. Deployment Kit Design

### A. Deployment Goal
*   Astra production deployment should ship as a **self-contained, OS-specific kit**.
*   The kit should not rely on ad hoc pip installs on the destination host.
*   Broker credentials and mutable runtime config remain externalized via env/config files and auth mounts.

### B. Kit Contents
Each Astra kit should include:
*   `services/strategy_runtime/`
*   required `packages/trading_core/` modules
*   pinned Python runtime or prebuilt virtual environment
*   pinned dependency wheelhouse, including **TA-Lib**
*   startup scripts for API/runtime launch
*   config templates and sample env files
*   health-check or smoke-test command

### C. Build Strategy
*   Build **one kit per target OS/Python combination**.
*   Do not assume one universal kit can serve Windows and Linux because binary dependencies such as TA-Lib are platform-specific.
*   Prefer Python **3.11** or **3.12** for the first TA-Lib production kit, rather than 3.14, to reduce binary wheel risk.
*   Prefer a reproducible build script that assembles a runtime folder or zip archive over manual copy/install steps.
*   Current implementation status: `scripts/build_astra_kit.ps1` stages the Astra runtime, docs, config templates, launch scripts, and optional wheelhouse downloads.
*   Package validation should include: import checks, runtime boot, indicator backend check, and a paper/replay smoke test.

---

## 6. Resilience & Error Handling

### A. Zero-DB Mode Logic
*   **`DatabaseManager`** catches connection exceptions and returns `None` for the connection pool.
*   **Downstream Services** check for `pool is None` and gracefully skip DB operations, ensuring the app remains operational in cloud/offline environments.

### B. Self-Healing (State Sync)
*   **Task**: Astra runs a background sync every 15 minutes.
*   **Action**: Calls `Adapter.get_positions()` and `Adapter.get_orders()`. If the broker's real state != Astra's in-memory record, it logs a `CRITICAL_MISMATCH` and triggers a Telegram alert.
