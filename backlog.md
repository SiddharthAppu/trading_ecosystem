# 📅 Project Backlog

This document tracks upcoming features, improvements, and bugs to address in the unified trading platform.

## 🎯 High Priority
- [ ] **Unified Authentication Manager**: Centralize Fyers/Upstox token handling into a single package.
- [ ] **Cross-App Navigation**: Ensure Historical UI and Forge UI share a consistent sidebar or header to switch between them.
- [ ] **End-to-End Testing**: Create a suite of tests that verify the full flow (Downloader -> Replay -> Execution).

## 🛠️ Infrastructure Improvements
- [ ] **Database Migration (TimescaleDB)**: Finalize unified schema for options historical and live tick data in TimescaleDB.
- [ ] **Containerization (Docker)**: Create a `docker-compose.yml` to simplify starting the entire stack (DB, Services, UI).
- [ ] **Enhanced Logging**: Centralized logging service that aggregates logs from all microservices.

## 📈 Feature Requests
- [ ] **Real-time Greeks Calculation**: Integrate IV and Greeks calculation into `trading_core` using `py_greeks`.
- [ ] **Performance Analytics**: Add a "PnL & Drawdown" dashboard to the Execution UI.
- [ ] **Strategy Builder (Drag-and-Drop)**: Visual strategy builder integration from StrategyForge.

## 🧹 Technical Debt
- [ ] **Unify Dependency Versions**: Ensure all packages/services use matching versions of common libraries (Pandas, Numpy, etc).
- [ ] **Refactor Data Collector**: Decouple provider-specific logic into cleaner plugin-style adapters.
