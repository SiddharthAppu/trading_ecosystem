# 🏁 Project Progress

This document tracks the milestones achieved during the consolidation and development of the trading platform.

## 🚀 Recent Milestones (Summary)
| Phase | Feature | Status | Date |
| :--- | :--- | :--- | :--- |
| **0** | **Consolidation** | ✅ Completed | 2026-04-06 |
| **1** | **Trading Core (v0.1.0)** | 🛠 In Progress | 2026-04-06 |
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

## 🛠 Currently In Progress
- **Event Bus Integration**: Migrating all services to use the asynchronous event bus in `trading_core.events`.
- **Dashboard UI Enhancements**: Finalizing the two-column layout in the Historical Dashboard for screenshot viewing.
- **Provider Payload Parity Hardening**: Continue validating symbol-level payload differences and fallback extraction logic for both providers.

## 📅 Roadmap Overview
1.  **Q2 2026**: Fully automated data recording and replay.
2.  **Q2 2026**: Strategy execution engine with live paper-trading capabilities.
3.  **Q3 2026**: Integration with multiple broker providers (Fyers, Upstox, etc).
4.  **Q4 2026**: Alpha release of Strategy Builder (Drag-and-Drop).

---
*Last updated: 2026-04-12*
