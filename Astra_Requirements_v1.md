# Astra: Lightweight Cloud Trading Executor (V1.1)
**Project Status**: Requirements & Design Phase (Updated)
**Primary Mission**: High-reliability, low-latency strategy execution on cloud infrastructure with zero local DB dependency and enriched execution journaling.

---

## 1. System Architecture (The "Zero-DB" Model)

### A. Component Boundaries
*   **`trading_core` (The Foundation)**: 
    *   Owns **Broker Adapters**: Standardized logic for Fyers/Upstox API calls.
  *   Owns **Broker Sync**: Methods to fetch live positions, order status, order book, available funds, and margin directly from Broker API to re-sync Astra's memory.
  *   Owns **Indicator Facade**: A stable analytics API that can switch between in-house and library-backed implementations without changing strategy code.
*   **`strategy_runtime` (Astra Engine)**:
    *   Owns **State Machine**: Tracks current positions and pending orders in memory using a custom schema.
    *   Owns **Execution Journaling**: Manages the `journal.jsonl` logic.
  *   Owns **Supervisor Loop**: Periodic reconciliation between journal state, in-memory state, and broker truth.
*   **`data_collector` (The Collector)**:
    *   Owns **WebSocket Management**: Maintains the persistent data pump using `trading_core` adapters.

---

## 2. Core Data Structures

### A. Market Ticks (Tick-to-File)
Ticks are stored in a rolling CSV format: `ticks_{date}.csv`.
**Schema**: `timestamp,symbol,price,volume,oi,delta,theta,bid,ask`
*   `oi`: Open Interest (for Options).
*   `delta/theta`: Key Greeks captured from the live stream.
*   **Timestamp**: `ISO 8601` (e.g., `2026-04-27T10:00:00.000Z`) to ensure seamless EOD import into TimescaleDB.

### B. Execution Journal (The Source of Truth)
Orders, signals, and fills are stored in `journal.jsonl`. Every entry includes mandatory context.

**Common Metadata for all Entries**:
*   `strategy`: Name of the algorithm (e.g., "IronCondor_V1").
*   `timeframe`: The candle aggregation used (e.g., "5m").
*   `symbol`: The instrument being traded.
*   `basket_id`: UUID used to group multiple legs/orders into a single trade concept.

**Sample Signal Entry**:
```json
{
  "ts": "2026-04-27T10:00:00Z", 
  "event": "INDICATOR_PASSED", 
  "symbol": "NIFTY24APR22000CE",
  "data": {"indicator": "RSI_14", "value": 72.5, "threshold": 70, "action": "OVERBOUGHT"},
  "basket_id": "bask-999"
}
```

**Sample Order Entry**:
```json
{
  "ts": "2026-04-27T10:00:01Z", 
  "event": "ORDER_PLACED", 
  "symbol": "NIFTY24APR22000CE",
  "data": {"order_id": "brk-456", "side": "SELL", "qty": 50, "price": 120.5},
  "basket_id": "bask-999"
}
```

**Recovery Constraint**:
*   Journaled order records must persist broker order identifiers and enough metadata to reconcile open broker orders after restart.

---

## 3. Real-time Intelligence

### Telegram Messaging Schema
*   **Priority: High (🚨 Alert)**: Fills, Liquidations, Risk Breaches.
*   **Priority: Med (📝 Info)**: `INDICATOR_PASSED` signals, Order placements.
*   **Priority: Low (📊 Heartbeat)**: Hourly PnL summary, WebSocket health.

### Indicator Calculation
*   **Sliding Windows**: Maintained in memory. 
*   **Verification**: On startup, Astra can query the Broker API for the last `N` candles to "warm up" indicators without needing a local DB.

### Indicator Backend Direction
*   **Current**: In-house EMA, SMA, RSI, and MACD calculations inside `trading_core.analytics`; `py_vollib` for option greeks.
*   **Recommended**: Use **TA-Lib** as the preferred backend for standard indicators behind an internal wrapper.
*   **Fallback**: Keep in-house implementations for deterministic fallback and regression comparison.
*   **Non-Goal**: Do not couple the live runtime directly to pandas-heavy research libraries.
*   **Integration Timing**: Integrate TA-Lib after the facade layer and parity tests are in place, but before freezing the production deployment kit format.
*   **Current Status**: Backend selection support is now present in the analytics layer; parity validation and packaging validation remain pending.

---

## 4. Key Performance Requirements
*   **Sync Capability**: Astra must be able to "Self-Heal" by comparing its memory state against the Broker API positions at 15-minute intervals.
*   **Basket Atomic Operations**: If one leg of a basket fails to place, Astra must log a `CRITICAL` signal and attempt to cancel/reverse the other legs.
*   **Broker Visibility**: Runtime status endpoints must surface broker-side positions, order book, available funds, and margin for operators.
*   **Indicator Safety**: Any migration to a third-party indicator library must be gated by parity tests against representative replay datasets.

---

## 5. Deployment Kit Requirements
*   **Deliverable Shape**: Astra should be distributable as an OS-specific runtime kit rather than a set of manual install instructions.
*   **Bundled Dependencies**: The kit must include pinned Python dependencies, including TA-Lib, so the destination host does not need ad hoc package installation.
*   **Kit Builder**: A repeatable build script must assemble code, dependencies, startup scripts, and config templates into the final deliverable.
*   **Preferred Baseline**: Target Python **3.11** or **3.12** for the first TA-Lib-based production kit.
*   **Immutable Bundle + External Config**: The code/dependency bundle should be immutable, while secrets and broker auth remain mounted or injected separately.
*   **Release Validation**: Each built kit must pass smoke tests for import health, runtime startup, and indicator backend availability.
