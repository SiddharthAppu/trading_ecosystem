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
- [x] **TA-Lib Integration (2026-04-28)**: TA-Lib 0.6.8 confirmed installed; fixed `_to_talib_input()` to return `np.ndarray`; analytics facade selects TA-Lib automatically when available (auto mode) with silent in-house fallback.
- [ ] **Astra Kit Hardening**: Pin dependency versions, build the offline wheelhouse, and add smoke tests to the kit output.
- [x] **Journal Recovery on Startup (2026-04-28)**: Added `JournalManager.recover_state()` to parse `ORDER_FILL` entries from `journal.jsonl`; `StrategyRuntime._recover_from_journal()` replays fills into portfolio on every startup.
- [x] **Self-Heal Supervisor Loop (2026-04-28)**: Replaced bare `try/raise` in `run()` with a supervised restart loop (max 5 restarts, linear backoff); transient errors now self-recover instead of halting.
- [x] **Broker Status API Endpoint (2026-04-28)**: Added `StrategyRuntime.get_broker_status()` (async, calls `get_available_funds`, `get_portfolio_status`, `get_orders` on the trading adapter via `asyncio.to_thread`); exposed at `GET /broker/status` in server.
- [x] **Live Paper Launcher Added (2026-04-28)**: Added `scripts/start_strategy_runtime_live_paper.ps1` plus `config/strategy_runtime.paper_live.env(.example)` for standalone broker-feed paper execution on 5-minute bars.
- [x] **Upstox File Capture Launcher Added (2026-04-28)**: Added `scripts/start_upstox_tick_capture_file.ps1` and enhanced `scripts/lib/quick_live_recorder.py` (`--max-symbols`, explicit flat-file spooling message) to support ATM ±21 CE/PE operator runs.
- [x] **NIFTY Trend Options Strategy (2026-04-28)**: Implemented `services/strategy_runtime/strategies/nifty_trend_options/` with EMA+MACD trend detection (bullish→CE, bearish→PE), ATM±N strike scan for premium near Rs 200, 2:1 RR exits (risk = 50% of entry, target = entry + 2×risk, stop = entry − risk), and human-readable decision logging to `logs/strategy_runtime/nifty_trend_decisions_{date}.txt`.
- [x] **EOD Import Utility (2026-04-28)**: Added `scripts/lib/import_ticks_to_db.py` to manually import captured tick CSV files from `logs/ticks/` into `broker_upstox.market_ticks` table, with `--date`, `--dir`, `--dry-run`, `--batch-size` flags and asyncpg bulk insert.
- [ ] **Basket Failure Recovery**: Add atomic handling for multi-leg placements, including rollback or compensating exits.

## Astra Gap Analysis (Standalone Desktop Run - 2026-04-28)
| Requirement | Current State | Gap | Priority |
| :--- | :--- | :--- | :--- |
| Install Astra kit in any folder and run | Kit scaffold exists via `build_astra_kit.ps1` | Add path-agnostic launchers + preflight validation + one-command startup guide | P0 |
| Live paper trading (not replay) | Runtime and paper executor exist | Add dedicated live-paper launcher and env template defaults for broker feed | P0 |
| Journal all paper trades | Journal logging exists (`ORDER_PLACED`, `ORDER_FILL`, signals) | Add explicit user guide runbook and log location guarantees in kit | P1 |
| Capture options ticks to file during day | Daily recorder writes to DB via data_collector flow | Add standalone file-based capture profile for Upstox (ATM ±21 CE/PE) | P0 |
| Manual EOD import from text into DB | Verification + aggregation scripts exist around DB-first flow | Add explicit file->DB import utility for standalone captured files | P0 |
| NIFTY50 options trend strategy (5m, premium ~200, RR 2:1) | Baseline `ema_cross` exists | Implement strategy module + strike selector from captured option stream + risk model exits | P0 |
| Strategy reasoning trace in text | Runtime has event/journal logs | Add dedicated human-readable decision log for every signal decision step | P1 |

### Delivery Sequence For Tomorrow Readiness
1. ✅ P0: Standalone live-paper launcher + config template.
2. ✅ P0: Upstox ATM ±21 CE/PE tick capture to file.
3. ✅ P0: NIFTY50 5m trend strategy with premium-near-200 strike selection and 2:1 RR exits.
4. ✅ P0: EOD manual import utility from captured file(s) to DB.
5. 🛠 P1: Strategy reasoning text log (decision log implementation complete; pending UX polish in kit).

## 🛠 Currently In Progress
- **Astra Kit Hardening**: Pin dependency versions, build the offline wheelhouse, and add smoke tests to the kit output.
- **Fyers/Upstox Account-Query Methods**: Implement `get_orders`, `get_available_funds`, `get_margin`, `get_portfolio_status` for parity with ZerodhaAdapter.

## 📅 Roadmap Overview
1.  **Q2 2026**: Fully automated data recording and replay.
2.  **Q2 2026**: Strategy execution engine with live paper-trading capabilities.
3.  **Q3 2026**: Integration with multiple broker providers (Fyers, Upstox, etc).
4.  **Q4 2026**: Alpha release of Strategy Builder (Drag-and-Drop).

---
*Last updated: 2026-04-28 (NIFTY trend options strategy, EOD import utility, decision logging, paper_live.env configured with nifty_trend_options)*
