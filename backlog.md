# 📅 Project Backlog

This document tracks upcoming features, improvements, and bugs to address in the unified trading platform.

## 🎯 High Priority
- [ ] **Greeks Normalization Pipeline (Phase 2)**: Add strict field-level reconciliation, null-rate monitoring, and replay-grade validation over provider payload drift.
- [ ] **Provider Payload Parity Hardening**: Continue validating symbol-level payload differences and fallback extraction logic for both providers.
- [ ] **Master Recorder Supervisor**: Add auto-restart, per-worker log files, and alarm hooks for failed child processes in `scripts/master_recorder.py`.
- [ ] **Unified Authentication Manager**: Centralize Fyers/Upstox token handling into a single package.
- [ ] **Cross-App Navigation**: Ensure Historical UI and Forge UI share a consistent sidebar or header to switch between them.
- [ ] **End-to-End Testing**: Create a suite of tests that verify the full flow (Downloader -> Replay -> Execution).

## 🛠️ Infrastructure Improvements
- [ ] **Provider Field Parity Matrix**: Publish and enforce a mapping contract for Fyers vs Upstox websocket fields (ltp, depth, volume, greeks).
- [ ] **Database Migration (TimescaleDB)**: Finalize unified schema for options historical and live tick data in TimescaleDB.
- [ ] **Containerization (Docker)**: Create a `docker-compose.yml` to simplify starting the entire stack (DB, Services, UI).
- [ ] **Enhanced Logging**: Centralized logging service that aggregates logs from all microservices.

## 📈 Feature Requests
- [ ] **Real-time Greeks Calculation**: Integrate IV and Greeks calculation into `trading_core` using `py_greeks`.
- [ ] **Performance Analytics**: Add a "PnL & Drawdown" dashboard to the Execution UI.
- [ ] **Strategy Builder (Drag-and-Drop)**: Visual strategy builder integration from StrategyForge.
- [ ] **DB Management UI (Phase 2)**: Add filtered export (CSV), table pagination, and quick toggles such as "show only tables with gaps".

## 🧹 Technical Debt
- [ ] **Unify Dependency Versions**: Ensure all packages/services use matching versions of common libraries (Pandas, Numpy, etc).
- [ ] **Refactor Data Collector**: Decouple provider-specific logic into cleaner plugin-style adapters.
