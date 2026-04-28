# Astra: Lightweight Cloud Trading Executor
**Project Status**: Requirements & Design Phase
**Primary Mission**: High-reliability, low-latency strategy execution on cloud infrastructure with zero local DB dependency.

---

## 1. System Architecture (The "Zero-DB" Model)
Astra operates as a standalone service that leverages `trading_core` for connectivity and `strategy_runtime` for execution logic.

### Role of `trading_core` (The Foundation)
*   **Broker Adapters**: Standardized API for Fyers/Upstox. Handles auth, rate-limiting, and WebSocket reconnection.
*   **Analytics Engine**: Provides pure-math functions for Greeks (Black-Scholes) and technical indicators.
*   **Common Models**: Shared dataclasses for `Tick`, `Bar`, `Order`, and `Position`.
*   **Symbol Resolver**: Maps human-readable symbols (e.g., "NIFTY24APR22000CE") to broker-specific tokens.

### Role of `strategy_runtime` (The Engine)
*   **Execution Loop**: Manages the main "Tick-to-Trade" cycle.
*   **State Machine**: Tracks current positions and pending orders in memory.
*   **Journaler**: Intercepts every event and flushes it to a local flat file.
*   **Risk Guard**: Implements standard deviations-based strikes (Iron Condor logic) and SL/TP checks.

---

## 2. Core Data Structures

### A. Market Ticks (Tick-to-File)
Ticks are stored in a rolling CSV format: `ticks_{date}.csv`.
Format: `timestamp,symbol,price,volume,bid,ask`
*   `ts`: ISO Timestamp (UTC)
*   `sym`: Symbol
*   `p`: Last Traded Price
*   `v`: Cumulative Volume
*   `b`: Best Bid
*   `a`: Best Ask

### B. Execution Journal (The Source of Truth)
Orders and fills are stored in `journal.jsonl` (JSON Lines) for easy parsing and recovery.
Example:
```json
{"ts": "2026-04-27T10:00:01Z", "event": "ORDER_PLACED", "data": {"id": "123", "side": "BUY", "qty": 50, "price": 22500}}
{"ts": "2026-04-27T10:00:02Z", "event": "ORDER_FILL", "data": {"id": "123", "fill_qty": 50, "fill_price": 22505}}
```

---

## 3. Real-time Intelligence

### Telegram Messaging Schema
*   **Priority: High (🚨 Alert)**: Fills, Liquidations, Risk Breaches, API Disconnects.
*   **Priority: Med (📝 Info)**: Strategy entry/exit signals, Order placements.
*   **Priority: Low (📊 Heartbeat)**: Hourly PnL summary, WebSocket health status.

### Indicator Calculation
*   **Memory-Efficient Windows**: Astra maintains a sliding window of the last `N` bars in a `deque`.
*   **On-the-Fly Aggregation**: Ticks are aggregated into 1m/5m bars in memory.
*   **Analytics Hook**: Every time a bar completes, `trading_core.analytics` is called to compute EMA, RSI, or Greeks.

---

## 4. Key Performance Requirements
*   **DB-Less**: Must start and run even if the PostgreSQL/TimescaleDB environment is completely offline.
*   **Low Footprint**: Target < 512MB RAM for the entire runtime.
*   **Auto-Recovery**: On restart, Astra must read `journal.jsonl` to reconstruct its current "Net Position" before resuming the strategy.
