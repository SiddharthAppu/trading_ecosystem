# Astra User Guide (Standalone Desktop, Paper Trading)

Version: 2026-04-28
Scope: Run Astra as a standalone desktop kit, do paper trading, keep a trade journal, capture option ticks to file, and manually import to DB after EOD.

## 1. What This Guide Covers

This guide targets the following operating model:
- Paper trading only (no live order placement).
- Market source from live broker data (Upstox for tick capture).
- Underlying focus: NIFTY50.
- Strategy timeframe: 5-minute bars.
- Option universe: ATM plus/minus 21 strikes for CE and PE.
- Entry instrument: option with premium nearest to Rs 200.
- Exit model: fixed reward:risk = 2:1.
- Capture ticks to text file during day.
- Import captured file into DB manually after market close.

## 2. Current Capability Snapshot

Available now:
- Strategy runtime service with paper execution.
- Journal logging for indicator, order, and fill events (`jsonl`).
- Runtime self-heal restart loop and broker status endpoint.
- TA-Lib-backed indicator facade.
- One-click live-paper launcher (`scripts/start_strategy_runtime_live_paper.ps1`).
- File-first tick capture launcher (`scripts/start_upstox_tick_capture_file.ps1`).
- NIFTY trend options strategy (`nifty_trend_options`) with premium-near-200 selection and 2:1 reward:risk exits.
- Manual file-to-DB import utility (`scripts/lib/import_ticks_to_db.py`).
- Astra kit builder (`scripts/build_astra_kit.ps1`).

## 3. Desktop Kit Build And Install

Build kit from workspace root (fast path, no wheelhouse):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_astra_kit.ps1 -Version v1
```

Build kit with offline wheels (recommended for machine-to-machine install):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_astra_kit.ps1 -Version v1 -IncludeWheelhouse
```

Expected output folder:
- `dist\astra-kit-v1-windows\`

Current workspace build status:
- Kit created at `dist\astra-kit-v1-windows\`.

Install on desktop (or any path):
1. Copy `dist\astra-kit-v1-windows` to target machine (or move to any folder on same machine).
2. Open PowerShell in kit root (`astra-kit-v1-windows`).
3. Create virtual environment:

```powershell
python -m venv .venv
```

4. Activate venv:

```powershell
.\.venv\Scripts\Activate.ps1
```

5. Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r .\services\strategy_runtime\astra-kit-requirements.txt
```

6. If wheelhouse is present (offline install), use:

```powershell
python -m pip install --no-index --find-links .\wheelhouse -r .\services\strategy_runtime\astra-kit-requirements.txt
```

7. Ensure auth/token files are present under `config\auth`.
8. Ensure `config\.env` has `DATABASE_URL` if you want EOD DB import.
9. Run runtime and tick-capture launchers from kit root.

Authentication behavior in live-paper launcher:
- `start_strategy_runtime_live_paper.ps1` now performs broker auth validation before startup.
- If token is missing/invalid, it prints broker login URL and prompts for auth code.
- Non-interactive mode: `-NonInteractiveAuth` fails fast when auth is missing.
- Emergency bypass (not recommended): `-SkipAuthCheck`.

## 4. Runtime Configuration (Paper Trading)

Core env intent:
- Feed source from broker.
- Trading provider forced to paper.
- Strategy timeframe set to 5m.
- Symbol set to NIFTY50 index mapping used by broker adapter.

Recommended runtime env keys:
- `STRATEGY_RUNTIME_FEED_SOURCE=broker`
- `STRATEGY_RUNTIME_PROVIDER=upstox`
- `STRATEGY_RUNTIME_TRADING_PROVIDER=paper`
- `STRATEGY_RUNTIME_SYMBOL=<NIFTY50 symbol expected by adapter>`
- `STRATEGY_RUNTIME_TIMEFRAME=5m`
- `STRATEGY_RUNTIME_STRATEGY=nifty_trend_options` (new strategy module)

## 5. Daily Operating Flow (Tomorrow Plan)

### Step A: Start Astra Runtime (paper)
- Start strategy runtime API/service using live broker feed and paper executor.
- Confirm health/status endpoints respond.
- Confirm journal file is created under `logs\\strategy_runtime\\`.

Command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_strategy_runtime_live_paper.ps1
```

### Step B: Start Tick Capture To File
- Start Upstox option tick capture for ATM +/- 21 strikes, both CE and PE.
- Persist each tick to text format (`csv` by symbol/day under current recorder implementation).


Command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_upstox_tick_capture_file.ps1 -StrikeCount 21 -Mode full
```

Optional explicit expiry list:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_upstox_tick_capture_file.ps1 -Expiries 2026-05-05,2026-05-12 -StrikeCount 21 -Mode full
```
- Ensure rolling file naming by date and optional hour chunking.

### Step C: Strategy Evaluation And Paper Trades
- Build 5-minute bars for NIFTY50 from incoming market data.
- Determine trend direction.
- Pick CE or PE based on trend direction.
- Among candidate strikes, choose the contract with premium nearest Rs 200.
- Place paper order.
- Compute stop-loss and target such that reward:risk = 2:1.
- Exit at target, stop, or strategy-defined invalidation.
- Log every decision step to a human-readable text file and to journal JSONL.

### Step D: End Of Day
- Stop runtime and recorder cleanly.
- Validate that tick text files exist and are non-empty.
- Run manual import utility to load file data into DB.
- Run verification checks (counts, symbol coverage, timestamp sanity).

Import command example:

```powershell
python .\scripts\lib\import_ticks_to_db.py --date 2026-04-28 --dir .\logs\ticks
```

## 6. Logging And Artifacts You Should See

Required files:
- Strategy runtime logs: `logs\strategy_runtime\runtime.log`
- Strategy journal: `logs\strategy_runtime\*_journal.jsonl`
- Strategy decision text log: `logs\strategy_runtime\nifty_trend_decisions_<date>.txt`
- Tick capture files: `logs\ticks\<symbol>_<date>.csv`

Minimum acceptance checks:
- At least one strategy decision cycle logged after market open.
- Journal contains `ORDER_PLACED` and `ORDER_FILL` events for paper trades.
- Tick file contains ATM and nearby strike ticks for CE/PE.
- Manual import script reports inserted row counts by symbol/date.

## 7. Mapping To Existing Daily Capture Workflow

Existing workflow script:
- `scripts\run_daily_capture_eod_workflow.bat`
- `scripts\run_daily_capture_eod_workflow.ps1`

What remains to align with Astra standalone mode:
- Keep same market-hour orchestration behavior.
- Add/enable file sink mode in recorder path.
- Keep EOD verification and backup steps optional but available.
- Ensure capture and strategy runtime can run together without port/process conflicts.

## 8. Risks And Mitigations

Risk: Missing auth token at runtime.
- Mitigation: preflight checks for token file presence and auth reload endpoint.

Risk: Strategy runs but no valid strike near Rs 200.
- Mitigation: configurable premium tolerance (for example +/- Rs 20), otherwise skip trade and log reason.

Risk: Tick capture overload from broad symbol set.
- Mitigation: strict ATM +/- 21 filtering and buffered file writer.

Risk: File import schema drift.
- Mitigation: lock JSONL schema and validate before import.

## 9. Implementation Checklist

✅ Completed:
- Live-paper startup script for Astra runtime (`scripts/start_strategy_runtime_live_paper.ps1`).
- File-based option tick recorder profile for Upstox ATM ±21 CE/PE (`scripts/start_upstox_tick_capture_file.ps1`).
- `nifty_trend_options` strategy (5m trend, premium-near-200, RR 2:1) with decision logging to `logs/strategy_runtime/nifty_trend_decisions_{date}.txt`.
- Manual `scripts/lib/import_ticks_to_db.py` utility for EOD file→DB import.

P1 (Future):
- Add single-command operator script to run strategy plus recorder together.
- Add smoke-test script for kit validation in new install path.

---
Owner: Astra runtime track
Status: Core implementation complete; ready for day-1 live-paper testing

## 10. Pre-Market Testing (Tonight / Tomorrow Before Open)

Run these in order from kit root.

1. Environment smoke test:

```powershell
python -c "import trading_core; print('OK trading_core')"
python -c "from services.strategy_runtime.strategies.nifty_trend_options.strategy import StrategyImpl; print('OK strategy import')"
```

2. Runtime launcher test (without market dependency check):
- Start runtime in one terminal:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_strategy_runtime_live_paper.ps1
```

- Confirm log files are created under `logs\strategy_runtime`.
- Confirm API responds:

```powershell
curl http://localhost:8090/health
curl http://localhost:8090/status
curl http://localhost:8090/broker/status
```

3. Tick-capture launcher test:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_upstox_tick_capture_file.ps1 -StrikeCount 21 -Mode full -MaxSymbols 50
```

- Let it run 2-5 minutes.
- Confirm CSV files appear under `logs\ticks` and rows are being appended.

4. Strategy output test:
- Verify `logs\strategy_runtime\nifty_trend_decisions_<date>.txt` appears.
- Verify journal has `ORDER_PLACED` and `ORDER_FILL` entries once a signal occurs.

5. EOD import dry-run test:

```powershell
python .\scripts\lib\import_ticks_to_db.py --date 2026-04-28 --dir .\logs\ticks --dry-run
```

- Validate file detection and row counts.

6. EOD DB write test (if DATABASE_URL configured):

```powershell
python .\scripts\lib\import_ticks_to_db.py --date 2026-04-28 --dir .\logs\ticks
```

- Validate non-zero inserted rows and no schema errors.
