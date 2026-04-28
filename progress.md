# 🏁 Project Progress

This document tracks the milestones achieved during the consolidation and development of the trading platform.

## 🚀 Recent Milestones (Summary)
| Phase | Feature | Status | Date |
| :--- | :--- | :--- | :--- |
| **0** | **Consolidation** | ✅ Completed | 2026-04-06 |
| **1** | **Trading Core (v0.1.0)** | 🛠 In Progress | 2026-04-06 |
| **1A** | **Astra Runtime Foundation** | 🛠 In Progress | 2026-04-28 |
| **2** | **Historical Platform UI** | ✅ Completed | 2026-04-05 |
| **3** | **Data Collector** | ✅ Completed | 2026-04-05 |


## ✅ Completed Tasks
- [x] **Project Unification**: Consolidated `HistoricalDownload`, `OptionsStrategyTester`, and `StrategyForge` into `trading_ecosystem`.
- [x] **Monorepo Architecture**: Established the `apps/`, `packages/`, `services/` structure.
- [x] **Shared Logic Extraction**: Initial `trading_core` package created.
- [x] **Unified Configuration**: Core `.env` file for database and API credentials.
- [x] **Master Startup Script**: `start_platform.bat` updated to launch all services.
- [x] **Multi-Provider Expiry API**: Added `GET /expiries/list` in Data Collector for Fyers/Upstox expiry discovery.
- [x] **Headless Expiry CLI**: Added `scripts/list_expiries.py` to fetch expiries for one provider or both.
- [x] **Live Recorder Upgrade (CLI + Orchestration)**: `quick_live_recorder.py` now supports `--provider`, `--expiry`, `--strike-count`, and non-interactive mode.
- [x] **Master Recorder Launcher**: Added `scripts/master_recorder.py` to start 8 recorder workers (4 expiries x 2 providers).
- [x] **Live Greeks Capture + EOD Merge**: Recorder now persists provider Greeks into `broker_<provider>.options_greeks_live`, with merge utility `scripts/merge_provider_greeks_to_master.py` for `analytics.options_greeks_master`.
- [x] **End-Of-Day Health Check**: Added `scripts/verify_eod_live_capture.py` and batch wrapper for daily EOD tick/Greeks capture verification, with log output to `logs/eod_live_capture/`.
- [x] **Database Backup Automation**: Added `scripts/db_backup.py` for safe, rolling Docker-based TimescaleDB backups with retention and no downtime.
- [x] **Timezone Integrity Audit & Hardening (2026-04-12)**: Full UTC/IST codebase investigation. Confirmed no DB corruption (out-of-session rows traced to legitimate Muhurat/special-session dates). Patched 5 scripts: `quick_download.py`, `quick_option_chain.py`, `aggregate_ticks_to_1min.py`, `run_eod_tick_aggregation.bat`, `merge_provider_greeks_to_master.py`. Created reusable audit tooling: `scripts/audit_timezone_integrity.py` + `scripts/run_timezone_audit.bat`. **Known remaining limitation**: live tick/Greeks timestamps reflect collector *arrival time* (UTC), not exchange *event time* — accepted as minor latency lapse, no fix planned.
- [x] **Astra Broker Contract Expansion (2026-04-28)**: Extended `BrokerAdapter` with broker-account query capabilities required for runtime supervision and self-heal workflows: order status, order book, available funds, margin, and portfolio status.
- [x] **Zerodha Adapter Completion (2026-04-28)**: Implemented Zerodha historical candle download, quotes, option expiry discovery, option-chain strike selection, order placement, positions, order book, funds, margin, and normalized portfolio status using the Kite REST API plus instrument dump resolution.

## Astra Progress
- [x] **Astra Doc Baseline Captured**: Requirements and LLD now reflect the current `trading_core` plus `strategy_runtime` architecture rather than a purely conceptual design.
- [x] **Broker Capability Gap Identified**: Confirmed Astra needs broker-side state queries beyond `get_positions()` for real recovery and runtime introspection.
- [x] **Indicator Engine Baseline Audited**: Confirmed runtime currently uses in-house indicator functions in `trading_core.analytics` for EMA, SMA, RSI, and MACD, with `py_vollib` used only for option greeks.
- [x] **Indicator Library Upgrade Decision**: TA-Lib selected as Astra's preferred production indicator backend, with `trading_core.analytics` retained as the stable facade and in-house implementation kept as fallback/parity reference.
- [x] **TA-Lib Facade Skeleton Added**: `trading_core.analytics` now supports backend selection with safe fallback to in-house indicators when TA-Lib is unavailable.
- [x] **Astra Kit Builder Scaffold Added**: Added `scripts/build_astra_kit.ps1` and an Astra runtime dependency manifest to assemble an OS-specific kit skeleton in dry-run or real build modes.
- [ ] **TA-Lib Parity + Packaging Validation**: Add dataset parity checks and validate TA-Lib wheel/binary inclusion on the target production Python version.
- [ ] **Astra Kit Hardening**: Pin dependency versions, build the offline wheelhouse, and add smoke tests to the kit output.
- [ ] **Journal Recovery Implementation**: Reconstruct portfolio and pending-order state from `journal.jsonl` on startup.
- [ ] **Self-Heal Loop Implementation**: Periodically compare in-memory state with broker positions and orders, then emit actionable recovery alerts.
- [ ] **Basket Failure Recovery**: Add atomic handling for multi-leg placements, including rollback or compensating exits.

## 🛠 Currently In Progress
- **Event Bus Integration**: Migrating all services to use the asynchronous event bus in `trading_core.events`.
- **Dashboard UI Enhancements**: Finalizing the two-column layout in the Historical Dashboard for screenshot viewing.
- **Provider Payload Parity Hardening**: Continue validating symbol-level payload differences and fallback extraction logic for both providers.
- **Astra Runtime Hardening**: Aligning requirements, LLD, adapter capabilities, and runtime supervision features before implementing state recovery and self-heal loops.

## 📅 Roadmap Overview
1.  **Q2 2026**: Fully automated data recording and replay.
2.  **Q2 2026**: Strategy execution engine with live paper-trading capabilities.
3.  **Q3 2026**: Integration with multiple broker providers (Fyers, Upstox, etc).
4.  **Q4 2026**: Alpha release of Strategy Builder (Drag-and-Drop).

---
*Last updated: 2026-04-28*
