# 📅 Project Backlog

This document tracks upcoming features, improvements, and bugs to address in the unified trading platform.


## 🎯 High Priority
- [ ] **Astra Self-Heal Supervisor**: Poll broker positions and order book on a fixed cadence, compare against runtime memory, and emit recovery actions plus Telegram alerts on drift.
- [ ] **Astra Journal Recovery**: Rebuild positions, pending orders, and basket state from `journal.jsonl` during startup before strategy execution resumes.
- [ ] **Astra Broker Capability Parity**: Implement the expanded `BrokerAdapter` account-query methods consistently across Fyers and Upstox, not only Zerodha.
- [ ] **Astra Runtime Broker Status API**: Expose broker-side positions, orders, funds, and margin from `strategy_runtime` status endpoints for operational visibility.
- [ ] **Astra Indicator Backend Upgrade**: Put a stable adapter layer in front of technical indicators, integrate TA-Lib as the preferred backend, benchmark it against current in-house outputs, and migrate only after parity checks pass.
- [ ] **Astra Production Kit Generator**: Add a build script that emits an OS-specific Astra kit containing runtime code, pinned Python dependencies, TA-Lib, startup scripts, example env/config, and verification steps.
- [ ] **Astra Order Lifecycle Controls**: Add `cancel_order`, `modify_order`, and normalized trade/fill queries to `BrokerAdapter` for recovery workflows.
- [ ] **Greeks Normalization Pipeline (Phase 2)**: Add strict field-level reconciliation, null-rate monitoring, and replay-grade validation over provider payload drift.
- [ ] **Provider Payload Parity Hardening**: Continue validating symbol-level payload differences and fallback extraction logic for both providers.
- [ ] **Master Recorder Supervisor**: Add auto-restart, per-worker log files, and alarm hooks for failed child processes in `scripts/master_recorder.py`.
- [ ] **Unified Authentication Manager**: Centralize Fyers/Upstox token handling into a single package.
- [ ] **Cross-App Navigation**: Ensure Historical UI and Forge UI share a consistent sidebar or header to switch between them.
- [ ] **End-to-End Testing**: Create a suite of tests that verify the full flow (Downloader -> Replay -> Execution).
- [ ] **EOD Health Check Automation**: Integrate EOD health check into CI or nightly cron, with alerting for failures and summary dashboard.
- [ ] **Backup Monitoring & Restore Testing**: Add automated checks for backup completion, retention, and periodic restore validation to ensure DB recoverability.

## 🛠️ Infrastructure Improvements
- [ ] **Astra Instrument Resolver Cache**: Persist and refresh broker instrument catalogs centrally so adapter lookups do not rely on ad hoc per-provider logic.
- [ ] **Astra Offline Wheelhouse**: Build and version a wheelhouse for Astra dependencies, including TA-Lib, so production kit creation does not depend on live internet installs.
- [ ] **Provider Field Parity Matrix**: Publish and enforce a mapping contract for Fyers vs Upstox websocket fields (ltp, depth, volume, greeks).
- [ ] **Database Migration (TimescaleDB)**: Finalize unified schema for options historical and live tick data in TimescaleDB.
- [ ] **Containerization (Docker)**: Create a `docker-compose.yml` to simplify starting the entire stack (DB, Services, UI).
- [ ] **Enhanced Logging**: Centralized logging service that aggregates logs from all microservices.

## 📈 Feature Requests
- [ ] **Indicator Library Evaluation Matrix**: Compare TA-Lib, pandas-ta, stock-indicators, and vectorbt on correctness, install friction, speed, dependency surface, and maintainability for Astra.
- [ ] **Real-time Greeks Calculation**: Integrate IV and Greeks calculation into `trading_core` using `py_greeks`.
- [ ] **Performance Analytics**: Add a "PnL & Drawdown" dashboard to the Execution UI.
- [ ] **Strategy Builder (Drag-and-Drop)**: Visual strategy builder integration from StrategyForge.
- [ ] **DB Management UI (Phase 2)**: Add filtered export (CSV), table pagination, and quick toggles such as "show only tables with gaps".

## 🧹 Technical Debt
- [ ] **Unify Dependency Versions**: Ensure all packages/services use matching versions of common libraries (Pandas, Numpy, etc).
- [ ] **Refactor Data Collector**: Decouple provider-specific logic into cleaner plugin-style adapters.

## ⚠️ Known Limitations (Accepted)
- **Live Tick Timestamps are Arrival-Time, not Exchange-Time**: All timestamps written by `live_recorder.py` into `market_ticks` and `options_greeks_live` use `datetime.now(timezone.utc)` — this is the moment the collector receives the message, not the exchange's event timestamp. This introduces a small latency offset (typically milliseconds, occasionally more on congested feeds). No fix is planned in the near term; the offset is negligible for strategy backtesting and replay purposes.
