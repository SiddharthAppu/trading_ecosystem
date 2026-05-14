# Astra User Guide (Standalone Desktop, Paper Trading)

Version: 2026-05-11
Scope: Build and deploy Astra standalone kits; run paper trading with a live broker feed or historical replay; run offline backtests and parameter optimisation.

---

## Table of Contents

1. [What Astra Provides](#1-what-astra-provides)
2. [Kit Overview](#2-kit-overview)
3. [Prerequisites](#3-prerequisites)
4. [Building The Kits](#4-building-the-kits)
5. [Deploying A Kit](#5-deploying-a-kit)
6. [Replay Kit: Paper Trading With Historical Data](#6-replay-kit-paper-trading-with-historical-data)
7. [Backtest Kit: Offline Strategy Analysis](#7-backtest-kit-offline-strategy-analysis)
8. [Live-Paper Kit: Paper Trading With Live Broker Feed](#8-live-paper-kit-paper-trading-with-live-broker-feed)
9. [Strategy Reference: ema_cross](#9-strategy-reference-ema_cross)
10. [Risk Management & Stop Loss](#10-risk-management--stop-loss)
11. [Live Tick Capture (Zero-DB Mode)](#11-live-tick-capture-zero-db-mode)
12. [Configuration Reference](#12-configuration-reference)
13. [Telegram Alerts Setup](#13-telegram-alerts-setup)
14. [Journal Event Linking](#14-journal-event-linking)
15. [Logging And Expected Artifacts](#15-logging-and-expected-artifacts)
16. [Smoke Tests And Validation](#16-smoke-tests-and-validation)
17. [Risks And Mitigations](#17-risks-and-mitigations)
18. [FAQ](#18-faq)

---

## 1. What Astra Provides

Astra is a modular, paper-trading-first strategy runtime for NIFTY50 options. Key capabilities:

| Capability | Status |
|---|---|
| Live-paper strategy runtime (broker feed) | ✅ |
| Replay paper runtime (historical DB feed) | ✅ |
| Offline backtest script | ✅ |
| Parameter optimisation grid search | ✅ |
| NIFTY Trend Options strategy (premium-near-200, 2:1 RR) | ✅ |
| EMA Cross strategy (Trend momentum, Bullish stack) | ✅ |
| Journal JSONL with TradingView deep-links | ✅ |
| Telegram trade alerts | ✅ |
| File-based option tick capture (Zero-DB Mode) | ✅ |
| One-click kit builder script | ✅ |
| Unified Capture + Strategy Startup | ✅ |

---

## 2. Kit Overview

Astra ships as three focused kits, all built from the same source workspace.

### astra-replay-kit-v1-windows
**Use case:** Paper trade the NIFTY Trend Options strategy against stored historical data with no live broker needed.

Contents:
- `services/strategy_runtime/` — strategy execution engine
- `services/replay_engine/` — WebSocket server that streams historical 1-minute bars from TimescaleDB
- `packages/trading_core/` — shared models, adapters, event bus
- `scripts/` — launcher scripts
- `config/` — env files and credentials

### astra-backtest-kit-v1-windows
**Use case:** Run a full backtest or parameter optimisation over any date range using DB data, no running services needed.

Contents:
- `scripts/strategy_backtest.py` — single-run backtest
- `scripts/strategy_optimize.py` — grid search optimizer
- `packages/trading_core/` — shared models
- `config/` — DB credentials env
- `docs/` — strategy documentation and this user guide

### astra-kit-v1-windows (live-paper + replay-paper)
**Use case:** Paper trade using a real-time live broker feed (Upstox/Fyers) during market hours, **or** connect to an externally running replay engine for replay-paper mode.

Contents:
- `services/strategy_runtime/` — includes the replay option data resolver and `replay_ws` feed support
- `packages/trading_core/`
- `config/` — includes `strategy_runtime.paper_replay.env.example` and `strategy_runtime.paper_live.env.example`
- `scripts/start_live_capture_and_strategy.ps1` — **Unified launcher** (Data + Strategy)
- `scripts/start_strategy_runtime_live_paper.ps1` — Strategy-only live launcher
- `scripts/start_strategy_runtime_paper_replay.ps1` — replay-paper launcher (connects to external replay engine)
- `scripts/authenticate_broker.py`, `scripts/start_upstox_tick_capture_file.ps1`, `scripts/lib/master_recorder.py`

> **Important:** `astra-kit` does **not** bundle `services/replay_engine/`. To use replay-paper mode with this kit, the replay engine WebSocket server must be started separately — either from the workspace or from `astra-replay-kit`. The strategy runtime will connect to it via `STRATEGY_RUNTIME_REPLAY_WS_URL`.

---

## 3. Prerequisites

### On any machine running a kit

| Requirement | Minimum |
|---|---|
| Python | 3.10+ |
| PowerShell | 5.1+ |
| TimescaleDB (PostgreSQL) | Required for replay and backtest kits |
| Internet | Required for live-paper kit (broker API) |

For the **replay and backtest kits**, the database must be reachable and contain:
- `master_broker.ohlcv_1m` — 1-minute OHLCV bars for NIFTY50
- `master_broker.options_ohlc_1m_fromupstox` — 1-minute option OHLCV data

### config/.env (global credentials)

All kits read `config\.env` for database and Telegram credentials. Create this file in the kit's `config\` folder before running:

```dotenv
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trading_db
DB_USER=postgres
DB_PASSWORD=your_password
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/trading_db

# Telegram (optional – leave blank to disable)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## 4. Building The Kits

Run the following from the **workspace root** (where `scripts\build_replay_backtest_kits.ps1` lives).

### Build replay + backtest kits

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_replay_backtest_kits.ps1 -Version v1
```

To rebuild from scratch (removes existing output first):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_replay_backtest_kits.ps1 -Version v1 -Clean
```

Output directories (created under `dist\`):
```
dist\
  astra-replay-kit-v1-windows\
  astra-backtest-kit-v1-windows\
```

### Build live-paper kit

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_astra_kit.ps1 -Version v1
```

With offline Python wheels (for machines without internet):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_astra_kit.ps1 -Version v1 -IncludeWheelhouse
```

Output:
```
dist\
  astra-kit-v1-windows\
```

### What the build script copies

**Replay kit includes:**
- `services/strategy_runtime/` (full service + nifty_trend_options strategy)
- `services/replay_engine/` (WebSocket replay server)
- `packages/trading_core/` (shared library)
- `START_REPLAY_KIT.ps1` — one-click launcher at **kit root** (not scripts/)
- `scripts/start_strategy_runtime_paper_replay.ps1`
- `scripts/start_strategy_runtime_live_paper.ps1`
- `scripts/authenticate_broker.py`
- `config/strategy_runtime.paper_replay.env` + `.env` (if present in workspace)
- STRATEGY.md and ARCHITECTURE_DIAGRAMS.md

> `START_REPLAY_KIT.ps1` is sourced from `scripts/START_REPLAY_KIT.ps1` in the workspace but placed at the **kit root** during build so you can run `.\START_REPLAY_KIT.ps1` directly without navigating to a subdirectory.

**Backtest kit includes:**
- `scripts/strategy_backtest.py`
- `scripts/strategy_optimize.py`
- `services/strategy_runtime/` — offline adapter runner and strategy implementations used by the backtest/optimizer
- `packages/trading_core/`
- `START_BACKTEST_KIT.ps1` — one-click launcher at **kit root** (not scripts/)
- `config/.env` (if present in workspace)
- `docs/` — STRATEGY.md and this user guide

---

## 5. Deploying A Kit

Deployment is the same for all three kits.

### Step 1: Copy the kit folder

Copy the entire kit directory to the target machine (USB, network share, zip transfer):

```
dist\astra-replay-kit-v1-windows\   →   C:\Trading\astra-replay-kit\
```

### Step 2: Create the Python virtual environment

Open PowerShell inside the kit root folder:

```powershell
cd C:\Trading\astra-replay-kit
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### Step 3: Install dependencies

**Replay kit / live-paper kit:**

```powershell
pip install -r .\services\strategy_runtime\astra-kit-requirements.txt
pip install -e .\packages\trading_core
```

**Backtest kit:**

```powershell
pip install -r .\services\strategy_runtime\astra-kit-requirements.txt psycopg2-binary
pip install -e .\packages\trading_core
```

If offline (wheelhouse present):

```powershell
pip install --no-index --find-links .\wheelhouse -r .\services\strategy_runtime\astra-kit-requirements.txt
pip install --no-index --find-links .\wheelhouse -e .\packages\trading_core
```

### Step 4: Configure credentials

Edit `config\.env` with your database and (optionally) Telegram credentials. See [Section 3](#3-prerequisites) for the template.

### Step 5: Configure the strategy env file (replay kit)

Edit `config\strategy_runtime.paper_replay.env`:

```dotenv
STRATEGY_RUNTIME_FEED_SOURCE=replay_ws
STRATEGY_RUNTIME_PROVIDER=fyers
STRATEGY_RUNTIME_SYMBOL=NSE:NIFTY50-INDEX
STRATEGY_RUNTIME_TIMEFRAME=1m
STRATEGY_RUNTIME_STRATEGY=nifty_trend_options
STRATEGY_RUNTIME_LOT_QUANTITY=1
STRATEGY_RUNTIME_LOT_SIZE=75
STRATEGY_RUNTIME_INITIAL_CAPITAL=100000
STRATEGY_RUNTIME_CAPITAL_MODEL=non_compounding
STRATEGY_RUNTIME_STOP_LOSS_PCT=0.60
STRATEGY_RUNTIME_REPLAY_WS_URL=ws://localhost:8765
STRATEGY_RUNTIME_REPLAY_SPEED=5
STRATEGY_RUNTIME_REPLAY_START_TIME=2026-04-15T09:15:00+05:30
STRATEGY_RUNTIME_REPLAY_END_TIME=2026-04-15T15:30:00+05:30
TELEGRAM_ENABLED=false

# NIFTY Trend Options strategy parameters
NIFTY_PREMIUM_TARGET=200.0
NIFTY_PREMIUM_TOLERANCE=30.0
NIFTY_REWARD_RISK_RATIO=2.0
NIFTY_EMA_PERIOD=20
NIFTY_SMA_PERIOD=20
NIFTY_MACD_FAST=12
NIFTY_MACD_SLOW=26
NIFTY_MACD_SIGNAL=9
```

---

## 6. Replay Kit: Paper Trading With Historical Data

The replay kit streams stored 1-minute bars from TimescaleDB via a local WebSocket, feeds them into the strategy runtime, and simulates paper trades — all without touching a live broker.

### One-click start

From inside the replay kit root:

```powershell
.\START_REPLAY_KIT.ps1
```

This automatically:
1. Loads `config\.env` (DB + Telegram creds)
2. Loads `config\strategy_runtime.paper_replay.env` (strategy config)
3. Prints a **preflight summary** with absolute config paths, DB details, resolved replay source table, replay time window, and expected behavior
4. Calls the replay HTTP API to check how many replay rows are available for the current symbol/provider/time window
5. In default `interactive` mode, asks for confirmation before launch
6. Starts the **replay engine** (WebSocket on `ws://localhost:8765`)
7. Waits 3 seconds for it to initialise
8. Starts the **strategy runtime** (HTTP API on `http://localhost:8090`)
9. Polls `/status` every 5 seconds and prints a live progress line to the console
10. Writes a final end-of-run summary when the runtime exits
11. On Ctrl+C, cleanly shuts down both processes (runtime + replay engine), preventing orphaned background processes

### Confirmation modes

Default interactive mode:

```powershell
.\START_REPLAY_KIT.ps1
```

Explicit interactive mode:

```powershell
.\START_REPLAY_KIT.ps1 -ConfirmationMode interactive
```

Non-interactive mode for automation:

```powershell
.\START_REPLAY_KIT.ps1 -ConfirmationMode non-interactive
```

In `interactive` mode, the script pauses after preflight and asks:

```text
Proceed with replay launch? [Y/N]
```

If preflight found `0` rows, the launcher warns that replay may remain idle with `latest_bar=null`.

### Override replay date at launch

```powershell
.\START_REPLAY_KIT.ps1 -Date 2026-04-15
```

### Override config at launch

You can override the default configuration files if you have multiple strategy setups:

```powershell
# Point to a specific strategy config
.\START_REPLAY_KIT.ps1 -EnvFile "config\strategy_runtime.ema_cross.paper_replay.env"

# Point to custom global credentials (DB etc.)
.\START_REPLAY_KIT.ps1 -GlobalEnv "C:\Secrets\.env"
```

### Change strategy

```powershell
.\START_REPLAY_KIT.ps1 -Strategy ema_cross
```

### Start strategy runtime only (replay engine already running)

```powershell
.\START_REPLAY_KIT.ps1 -SkipReplayEngine
```

### What the console shows during replay

After launch, the console no longer shows raw uvicorn logs. Instead it shows structured progress lines such as:

```text
[PROGRESS][RUNNING] latest_bar=2026-04-15T09:32:00+05:30 close=22431.15 position=flat completed=False
```

Progress states:

| State | Meaning |
|---|---|
| `IDLE` | Runtime is up but has not received a replay bar yet |
| `RUNNING` | Replay bars are flowing and latest bar is advancing |
| `COMPLETED` | Replay stream finished normally |
| `ERROR` | Runtime or replay feed reported an error |

If status is not yet reachable, the launcher prints:

```text
[PROGRESS] Waiting for runtime status endpoint...
```

### What the launcher logs for each run

Each replay run writes a persistent summary file under:

```text
logs\run_summaries\replay_run_YYYYMMDD_HHMMSS.log
```

This run log includes:
- full preflight summary
- absolute paths for env and runtime files
- DB host/port/name/user and resolved replay source table
- preflight replay row count
- expected replay duration estimate
- progress snapshots while replay is running
- final end-of-run summary

The launcher also writes runtime process logs to:
- `logs\runtime_stdout.log`
- `logs\runtime_stderr.log`
- `logs\replay_engine.log`
- `logs\replay_engine_err.log`

### What the final summary tells you

When replay ends, the launcher writes a final summary including:
- launch start/end time
- total duration
- runtime exit code
- whether replay completed
- last replay bar timestamp and close
- final paper position
- runtime last error and replay error
- log file paths

This makes it easy to confirm whether the replay actually ran, ended early, or had no data.

### Manual two-terminal approach

Terminal 1 — start replay engine:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = ".\packages\trading_core"
python .\services\replay_engine\main.py
```

Terminal 2 — start strategy runtime:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = ".\packages\trading_core;.\services\strategy_runtime"
python .\services\strategy_runtime\server.py
```

### Verify it is running

```powershell
curl http://localhost:8090/health
curl http://localhost:8090/status
```

### Runtime API ports

| Service | Port | Protocol |
|---|---|---|
| Strategy Runtime API | 8090 | HTTP |
| Replay Engine | 8765 | WebSocket |

### How replay option data works

In replay mode, option chain and quote lookups are resolved from a historical DB table at the simulated timestamp, and no live broker quote API is called. By default, the resolver uses `master_broker.options_ohlc_1m_fromupstox`.

You can override the option quote source table with:

```dotenv
STRATEGY_RUNTIME_REPLAY_OPTIONS_TABLE=master_broker.options_ohlc_1m_fromupstox
```

This table override is independent of `STRATEGY_RUNTIME_REPLAY_DATA_TYPE` (which controls the underlying replay stream such as `ohlcv_1m` or `market_ticks`). The resolver is automatically injected by the runtime when `FEED_SOURCE=replay_ws`.

### Phase 1: Tick-based replay with 1m bar aggregation

By default the replay engine streams pre-aggregated 1-minute OHLCV bars (`ohlcv_1m`). When raw market ticks are available in `broker_fyers.market_ticks`, you can run a higher-fidelity replay that aggregates ticks into bars in real time.

**When to use tick-based replay:**
- The target date has rows in `broker_fyers.market_ticks` but `master_broker.ohlcv_1m` returns 0 rows.
- You want intra-bar price movement fidelity for entry/exit simulation.

**How to enable:**

In `config\strategy_runtime.paper_replay.env`:

```dotenv
# Tell the replay engine to stream raw tick events instead of OHLCV bars
STRATEGY_RUNTIME_REPLAY_DATA_TYPE=market_ticks

# Tell the runtime to aggregate ticks into 1-minute bars before feeding the strategy
STRATEGY_RUNTIME_INDICATOR_INPUT_MODE=bars_1m
```

**What happens internally:**

1. The replay engine reads rows from `broker_fyers.market_ticks` for the configured symbol/time window.
2. Each tick is emitted as a WebSocket message to the strategy runtime.
3. The runtime's `TickAggregator` accumulates ticks and emits a closed 1-minute OHLCV bar at the end of each minute.
4. The strategy sees clean 1-minute bars — identical to the `ohlcv_1m` path — no strategy code changes are needed.

**Verifying data availability before replay:**

```sql
-- Check tick count for a date
SELECT count(*) FROM broker_fyers.market_ticks
WHERE ts >= '2026-04-15 09:15:00+05:30'
  AND ts <  '2026-04-15 15:30:00+05:30'
  AND symbol = 'NSE:NIFTY50-INDEX';
```

**Indicator input mode values:**

| `STRATEGY_RUNTIME_INDICATOR_INPUT_MODE` | Effect |
|---|---|
| `bars_1m` (default) | Strategy receives pre-built 1m OHLCV bars directly (either from replay or live feed) |
| `ticks` | Strategy receives individual tick events (advanced, not used by nifty_trend_options) |

> When `REPLAY_DATA_TYPE=market_ticks` and `INDICATOR_INPUT_MODE=bars_1m`, the `TickAggregator` bridges the two: ticks in → 1m bars out. The source table in the run summary log will show `broker_fyers.market_ticks` instead of `broker_fyers.ohlcv_1m`.

---

## 7. Backtest Kit: Offline Strategy Analysis

The backtest kit reads directly from TimescaleDB and simulates the nifty_trend_options strategy signal logic over a date range, with no running services needed.

### One-click start (interactive date prompt)

```powershell
.\START_BACKTEST_KIT.ps1
```

Prompts for start and end dates, then runs the backtest and prints a trade-by-trade summary.

### Run with explicit dates

```powershell
.\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28
```

### Run parameter optimisation

```powershell
.\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28 -Mode optimize
```

### Quick Start: Optimize + Open Artifacts

Run optimization and then open the artifact index pages:

```powershell
# 1) Run optimize
.\START_BACKTEST_KIT.ps1 -From 2020-01-01 -To 2026-05-07 -Mode optimize

# 2) Open artifact pages
Start-Process .\ARTIFACT_INDEX_LATEST_RUN.html
Start-Process .\ARTIFACT_INDEX.html
```

If the HTML files are missing, generate them by rerunning the helper command/workflow used during your kit setup, or open artifact folders directly:

```powershell
ii .\logs\strategy_runtime
ii .\logs\run_summaries
```

### Optimizer range config (JSON)

By default, optimize mode loads parameter ranges from:

```text
config\strategy_optimize_ranges.json
```

You can pass a custom ranges file at launch:

```powershell
.\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28 -Mode optimize -OptimizerConfig "config\my_ranges.json"
```

`strategy_optimize_ranges.json` supports:
- `mode: "range"` with `values: [...]` for parameters to sweep.
- `mode: "fixed"` with `value: ...` for parameters kept constant.
- `early_stop` settings to probe only the first portion of bars and skip full runs when probe trades are zero.

Example fixed parameter:

```json
"ema_period": { "mode": "fixed", "value": 20 }
```

Show top 15 parameter combinations instead of default 10:

```powershell
.\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28 -Mode optimize -Top 15
```

### Override credentials at launch

```powershell
.\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28 -EnvFile "D:\Configs\trading_db.env"
```

### Reuse strategy config file from config directory

By default, `START_BACKTEST_KIT.ps1` also reads strategy metadata from:

```text
config\strategy_runtime.paper_replay.env
```

It picks these keys when present:
- `STRATEGY_RUNTIME_STRATEGY` -> backtest `--strategy-name`
- `STRATEGY_RUNTIME_TIMEFRAME` -> backtest `--timeframe`
- `STRATEGY_RUNTIME_LOG_FILE` -> backtest `--log-file`

Use a different strategy config file with:

```powershell
.\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28 -StrategyConfig "config\strategy_runtime.ema_cross.paper_replay.env"
```

CLI parameters always override values loaded from the strategy config file.

### Run scripts directly (bypass runner)

`START_BACKTEST_KIT.ps1` is an operator-friendly wrapper around direct script calls. It adds env loading, interactive date prompts, date format validation, smoke-mode normalization, and consistent argument assembly/summary output. The backtest kit now runs through the strategy-runtime offline adapter path only. Direct script invocation is still useful for automation and advanced custom runs.

Single backtest:

```powershell
.\.venv\Scripts\python.exe .\scripts\strategy_backtest.py --from 2026-04-01 --to 2026-04-28
```

Grid search optimisation:

```powershell
.\.venv\Scripts\python.exe .\scripts\strategy_optimize.py --from 2026-04-01 --to 2026-04-28 --top 10 --optimizer-config config\strategy_optimize_ranges.json
```

Custom symbol:

```powershell
.\.venv\Scripts\python.exe .\scripts\strategy_backtest.py `
  --from 2026-04-01 --to 2026-04-28 `
  --symbol "NSE_INDEX|Nifty 50"
```

### Backtest output

The backtest prints a summary table showing:
- Entry and exit timestamps
- Option symbol traded
- Entry/exit prices
- PnL per trade
- Cumulative PnL
- Win rate and total trades

The optimiser ranks parameter sets by net PnL. Useful parameters to tune:

| Parameter | Env Key | Default |
|---|---|---|
| EMA period | `NIFTY_EMA_PERIOD` | 20 |
| SMA period | `NIFTY_SMA_PERIOD` | 20 |
| MACD fast | `NIFTY_MACD_FAST` | 12 |
| MACD slow | `NIFTY_MACD_SLOW` | 26 |
| MACD signal | `NIFTY_MACD_SIGNAL` | 9 |
| Premium target (Rs) | `NIFTY_TARGET_PREMIUM` | 200.0 |
| Premium tolerance (Rs) | `NIFTY_PREMIUM_TOLERANCE` | 30.0 |
| Stop loss premium pct | `NIFTY_STOP_LOSS_PREMIUM_PCT` | 0.5 |

### Optimizer artifacts and HTML indexes

Optimize runs write most outputs under:
- `logs\strategy_runtime\` (probe and full `opt_*.jsonl` journals)
- `logs\run_summaries\` (launcher run summaries)

If present in kit root, open these helper pages:
- `ARTIFACT_INDEX.html` - full artifact list with relative links
- `ARTIFACT_INDEX_LATEST_RUN.html` - latest optimize run-focused list

```powershell
Start-Process .\ARTIFACT_INDEX.html
Start-Process .\ARTIFACT_INDEX_LATEST_RUN.html
```

---

## 8. Live-Paper Kit: Paper Trading With Live Broker Feed Or External Replay

The `astra-kit` supports three operating modes, plus replay-paper connectivity:

| Mode | Feed source | Replay engine needed? |
|---|---|---|
| Live-paper | Live broker (Upstox/Fyers) | No |
| Unified Capture + Strategy (Astra Studio) | Live broker + recorder orchestration | No |
| Live-live (advanced) | Live broker feed + live broker execution | No |
| Replay-paper | Historical DB via WebSocket | Yes — started externally |

`Replay-paper` in `astra-kit` is functionally the same runtime mode as the replay kit (historical bars over WebSocket). The difference is packaging: replay kit bundles and launches `services/replay_engine`, while `astra-kit` expects replay engine to be started externally.

### Mode 1: Live-paper (market hours)

#### Authenticate broker first

```powershell
.\.venv\Scripts\Activate.ps1
python .\scripts\authenticate_broker.py
```

Follow the printed URL to complete OAuth login. The token is saved to `config\auth\`.

#### Start live-paper runtime

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_strategy_runtime_live_paper.ps1
```

Or with explicit strategy:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_strategy_runtime_live_paper.ps1 -Strategy nifty_trend_options
```

### Mode 2: Unified Capture + Strategy (Astra Studio Mode)

This is the recommended mode for active paper trading sessions. It launches the Data Collector, starts the Master Recorder (to capture ticks), and starts your Strategy Runtime in one window.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_live_capture_and_strategy.ps1 -Strategy ema_cross
```

**What this does:**
1.  **Ensures Collector:** Starts Data Collector if not already running.
2.  **Starts Master Recorder:** Begins capturing ticks for the next 4 weekly expiries into `logs/ticks/` (CSV-first workflow).
3.  **Starts Strategy:** Launches the strategy engine in Paper Trading mode connected to the live broker feed.

Recorder persistence is configurable (`--enable-db true|false|default`). For low-latency sessions, recommended practice is CSV-first capture during market hours, then EOD import into DB.

### Mode 3: Live-live (advanced)

This mode places real broker orders while still using live market data. Use only after paper-mode validation and risk checks.

To enable live execution, set `STRATEGY_RUNTIME_TRADING_PROVIDER` to a live adapter (for example `zerodha`) in your live env file, then launch normally:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_strategy_runtime_live_paper.ps1 -Strategy ema_cross
```

Notes:
- Data provider (`STRATEGY_RUNTIME_PROVIDER`) and trading provider (`STRATEGY_RUNTIME_TRADING_PROVIDER`) are separate settings.
- A single runtime process uses one market-data provider at a time. If you need dual-provider capture, run recorder workers for both providers.
- Keep tick capture running to preserve auditability and support EOD DB import workflows.

---

## 9. Strategy Reference: ema_cross

The `ema_cross` strategy is a trend-following momentum strategy designed for NIFTY50.

### Entry Logic (Bullish Stack)
- **Condition:** `Price > EMA 20 > SMA 20`
- **Logic:** The strategy enters a LONG position when the price is trending above both its short-term exponential and medium-term simple moving averages.
- **Trigger:** Only triggers if no position is currently open.

### Exit Logic
- **Condition:** `Price < EMA 20`
- **Logic:** The strategy closes the position as soon as the price breaks the short-term trend line (EMA 20).

### Key Parameters
- `STRATEGY_RUNTIME_TIMEFRAME`: 5m (Standard)
- `STRATEGY_RUNTIME_INDICATORS`: `ema_20,sma_20`

---

## 10. Risk Management & Stop Loss

Astra enforces risk management at the **Infrastructure (Runtime) Level**, independent of the specific strategy code. This ensures safety even if a strategy has a logic bug.

### Global Safety Toggles
In your `.env` file, these parameters control the **RuntimeRiskManager**:

| Parameter | Default | Description |
|---|---|---|
| `STRATEGY_RUNTIME_STOP_LOSS_PCT` | `0.01` (1%) | Hard stop loss relative to entry price. |
| `STRATEGY_RUNTIME_TRAILING_STOP_PCT` | `0.015` (1.5%) | Automatically trails the price at a 1.5% distance. |
| `STRATEGY_RUNTIME_MAX_POSITION_LOTS` | `1` | Maximum lots allowed for any single symbol. |

**Important:** If the price hits your 1% Stop Loss, the **Engine** will force-exit the position and record a `STOP_LOSS_EXIT` in the journal, even if the strategy logic hasn't triggered an exit yet.

---

## 11. Live Tick Capture (Zero-DB Mode)

To ensure maximum performance and low latency during market hours, Astra uses a **Zero-DB Capture** strategy.

### How it works
- **Real-time Persistence:** Market ticks are streamed directly to symbol-specific CSV files.
- **Default Config:** `ASTRA_RECORDER_ENABLE_DB=false` is the default in Astra Kits.
- **Naming Convention:** `logs/ticks/{Clean_Symbol}_{YYYY-MM-DD}.csv`
- **Format:** `timestamp, symbol, price, volume, oi, delta, theta, bid, ask`

### EOD Synchronization
After the market closes, you can import these CSV files into your database for historical analysis:
```powershell
python .\scripts\lib\import_ticks_to_db.py --date 2026-05-06 --dir .\logs\ticks
```

---

## 12. Configuration Reference

### Example config files index

Comprehensive templates with extensive per-parameter descriptions:
- `config\strategy_runtime.explicit_replay.full.env.example` - full replay/runtime template with explicit source contract and fail-fast chunking controls.
- `config\strategy_runtime.explicit_live.full.env.example` - full live/broker runtime template with complete parameter vocabulary.
- `config\strategy_backtest.explicit_full.env.example` - full backtest template with explicit source contract and chunking controls.

Concrete defaults (Upstox-first) for quick start:
- `config\strategy_runtime.upstox.replay_ticks.default.env.example` - replay using Upstox tick table (`broker_upstox.market_ticks`).
- `config\strategy_runtime.upstox.replay_bars.default.env.example` - replay using Upstox bar table (`broker_upstox.ohlcv_1m`).

Notes:
- The concrete defaults use Upstox for provider, index symbol format, source tables, and options table.
- For backtest, pair one of the above with `scripts\strategy_backtest.py --from <YYYY-MM-DD> --to <YYYY-MM-DD>` and adjust source table/data kind as needed.

### strategy_runtime.paper_replay.env — key applicability by capital mode

Modes:
- `non_compounding`: Trade size remains `STRATEGY_RUNTIME_LOT_QUANTITY` lots. In adapter backtest/optimize runs, capital is refilled to baseline after losses.
- `compounding`: Trade size scales with available capital in lot increments.

`Applies To` indicates where each key is operationally relevant. Multiple codes mean the key is used across those kits/contexts.

Legend:
- `RP` = Replay Kit
- `BT` = Backtest Kit
- `LK` = LiveKit
- `Stra` = Strategy-specific parameter

| Key | Description | Applies To | Example |
|---|---|---|---|
| `STRATEGY_RUNTIME_FEED_SOURCE` | `broker` or `replay_ws` | `RP, LK` | `replay_ws` |
| `STRATEGY_RUNTIME_PROVIDER` | Broker provider namespace | `RP, LK` | `fyers` |
| `STRATEGY_RUNTIME_SYMBOL` | Underlying symbol | `RP, LK` | `NSE:NIFTY50-INDEX` |
| `STRATEGY_RUNTIME_TIMEFRAME` | Bar timeframe | `RP, BT, LK` | `1m` |
| `STRATEGY_RUNTIME_STRATEGY` | Strategy module name | `RP, BT, LK` | `nifty_trend_options` |
| `STRATEGY_RUNTIME_LOT_QUANTITY` | Base lots per trade; set `-1` for auto-lot mode | `RP, BT, LK` | `1` |
| `STRATEGY_RUNTIME_LOT_SIZE` | Units per lot for the instrument | `RP, BT, LK` | `75` |
| `STRATEGY_RUNTIME_INITIAL_CAPITAL` | Starting capital (Rs) | `RP, BT, LK` | `100000` |
| `STRATEGY_RUNTIME_CAPITAL_MODEL` | Position sizing capital mode | `RP, BT, LK` | `non_compounding` |
| `STRATEGY_RUNTIME_MAX_POSITION_LOTS` | Maximum lots allowed | `RP, LK` | `1` |
| `STRATEGY_RUNTIME_STOP_LOSS_PCT` | Stop loss % (0.60 = 60%) | `RP, LK` | `0.60` |
| `STRATEGY_RUNTIME_REPLAY_WS_URL` | Replay engine WebSocket URL | `RP, LK` | `ws://localhost:8765` |
| `STRATEGY_RUNTIME_REPLAY_SPEED` | Replay speed multiplier | `RP, LK` | `5` |
| `STRATEGY_RUNTIME_REPLAY_START_TIME` | ISO8601 replay start | `RP, LK` | `2026-04-15T09:15:00+05:30` |
| `STRATEGY_RUNTIME_REPLAY_END_TIME` | ISO8601 replay end | `RP, LK` | `2026-04-15T15:30:00+05:30` |
| `STRATEGY_RUNTIME_REPLAY_DATA_TYPE` | Data type streamed by replay engine | `RP, LK` | `ohlcv_1m` or `market_ticks` |
| `STRATEGY_RUNTIME_INDICATOR_INPUT_MODE` | How indicators receive data | `RP, LK` | `bars_1m` or `ticks` |
| `TELEGRAM_ENABLED` | Enable Telegram alerts | `RP, LK` | `false` |
| `NIFTY_PREMIUM_TARGET` | Target option premium (Rs) | `RP, BT, LK, Stra` | `200.0` |
| `NIFTY_PREMIUM_TOLERANCE` | Premium tolerance window (Rs) | `RP, BT, LK, Stra` | `30.0` |
| `NIFTY_REWARD_RISK_RATIO` | Exit target as multiple of stop | `RP, BT, LK, Stra` | `2.0` |
| `NIFTY_EMA_PERIOD` | EMA period for trend | `RP, BT, LK, Stra` | `20` |
| `NIFTY_SMA_PERIOD` | SMA period for trend | `RP, BT, LK, Stra` | `20` |
| `NIFTY_MACD_FAST` | MACD fast EMA | `RP, BT, LK, Stra` | `12` |
| `NIFTY_MACD_SLOW` | MACD slow EMA | `RP, BT, LK, Stra` | `26` |
| `NIFTY_MACD_SIGNAL` | MACD signal line | `RP, BT, LK, Stra` | `9` |

Capital + refill behavior in adapter backtest/optimize mode:
- `non_compounding`: uses configured lot quantity; when capital dips below initial capital after a closed trade, runtime emits `INITIAL_CAPITAL_REFILL` and tops capital back to baseline.
- `compounding`: lot quantity scales with available capital; refill occurs only if capital falls to or below zero, allowing continuity of simulation runs.
- **Auto-lot mode** (`STRATEGY_RUNTIME_LOT_QUANTITY=-1`): applies to both capital models. Each bar, effective lots = `floor(capital_available / (bar.close × lot_size))`, minimum 1. Overrides any fixed lot quantity.
- **Insufficient funds**: this skip check is applied in auto-lot mode (`STRATEGY_RUNTIME_LOT_QUANTITY=-1`). If capital cannot fund even one lot at bar close price and no position is open, the bar is skipped and an `INSUFFICIENT_FUNDS_SKIP` event is written to the journal. The run continues to subsequent bars. Summary output includes `insufficient_funds_skips` count.

### Maintenance reference — files to sync when config keys change

When adding or renaming a strategy runtime config key, update all of the following:

| File | Role |
|---|---|
| `services/strategy_runtime/config.py` | Canonical env key loader |
| `scripts/strategy_backtest.py` | CLI flag → strategy_params mapping |
| `scripts/strategy_optimize.py` | CLI flag → strategy_params mapping |
| `scripts/START_BACKTEST_KIT.ps1` | Backtest kit launcher defaults |
| `config/strategy_runtime.backtest_example.env` | Backtest sample config template |
| `Astra_UserGuide.md` Section 12 table | Applicability reference |

### config/.env — global credentials

| Key | Description |
|---|---|
| `DB_HOST` | PostgreSQL host |
| `DB_PORT` | PostgreSQL port (default 5432) |
| `DB_NAME` | Database name |
| `DB_USER` | Database user |
| `DB_PASSWORD` | Database password |
| `DATABASE_URL` | Full connection URL (overrides individual keys) |
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID (see Section 13) |

---

## 13. Telegram Alerts Setup

### Create a bot

1. Open Telegram and message `@BotFather`.
2. Send `/newbot` and follow the prompts.
3. Copy the `Bot Token` provided.

### Get your Chat ID

1. Send `/start` to your new bot.
2. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find `"chat": {"id": 123456789}` — that number is your Chat ID.

### Configure credentials

In `config\.env`:

```dotenv
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIjKlMnOpQrStUvWxYz
TELEGRAM_CHAT_ID=123456789
```

### Enable per-strategy

In `config\strategy_runtime.paper_replay.env`:

```dotenv
TELEGRAM_ENABLED=true
```

Alerts are sent on: ORDER_PLACED, ORDER_FILL, strategy errors. When `TELEGRAM_ENABLED=false` (default), no messages are sent even if credentials are present.

---

## 14. Journal Event Linking

Every order and signal decision is written to a JSONL journal at `logs\strategy_runtime\*_journal.jsonl`. Astra provides tools to bridge these logs into visual charting environments.

### TradingView Desktop & Deep-Links

The `journal_event_linker.py` tool generates a report with deep-links that can open your TradingView Desktop application directly to the exact candle where an event occurred.

**Enable Desktop Protocol:**
Set the environment variable `TRADINGVIEW_USE_DESKTOP_APP=true` before running the linker. This converts `https://` links into `tradingview://` deep-links.

### Generating Visual Reports

Run the linker tool to generate a Markdown report and a Pine Script marker file:

```powershell
# Set environment for high-precision links
$env:TRADINGVIEW_LAYOUT_ID="z9HWD4GU"
$env:TRADINGVIEW_USE_DESKTOP_APP="true"

python .\UtilTools\journal_event_linker.py `
  --journal .\logs\strategy_runtime\runtime_journal.jsonl `
  --output-md .\logs\strategy_runtime\journal_links.md `
  --output-json .\logs\strategy_runtime\journal_links.json `
  --output-sql .\logs\strategy_runtime\journal_links.audit.sql `
  --price-tolerance 0.05
```

**Generated Artifacts:**
1.  `journal_links.md`: An interactive table with BUY/SELL sides and deep-links.
2.  `journal_links.pine`: A **Pine Script v6** indicator containing your trade coordinates.
3.  `journal_links.audit.sql`: SQL audit script that compares journal prices against DB rows.

### SQL Audit: Cross-Verify Journal vs DB

The generated SQL includes four audit sections:
1.  **Option fill mismatch check** (mismatch-focused): compares `ORDER_FILL`/`FILL` prices to option `close` at-or-before `event_ts`.
2.  **Option fill summary**: grouped counts (`MATCH`, `PRICE_MISMATCH`, `MISSING_DB_ROW`).
3.  **Entry spot check (5m semantic)**: compares `ENTRY_PASSED` spot price to reconstructed 5m bucket close.
4.  **Entry spot check (strict 1m)**: compares `ENTRY_PASSED` spot price to latest 1m row at-or-before `event_ts`.

Use section 3 for backtest/replay semantic alignment; use section 4 for strict timestamp diagnostics.

#### Run the generated SQL in Python

```powershell
python - <<'PY'
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv('config/.env')
sql = open(r'logs/strategy_runtime/journal_links.audit.sql', encoding='utf-8').read()

conn = psycopg2.connect(os.environ['DATABASE_URL'])
try:
    with conn.cursor() as cur:
        cur.execute(sql)
        # If your SQL client executes one statement at a time, run each section separately.
finally:
    conn.close()
PY
```

#### Notes on data source metadata

`RUNTIME_HEADER` now records source metadata used by the linker SQL header:
- `source_mode` (`live`, `replay`, `backtest`, `optimize`)
- `provider`
- `source_db` (host/db name, masked credentials)
- `index_source_table`
- `options_source_table`

This helps confirm whether a journal was produced from live feed, replay feed, or offline backtest/optimize datasets.

### Visualising Trades in TradingView

To see your Astra trades overlaid on your TradingView charts:

1.  Open the generated `journal_links.pine` in a text editor and copy the code.
2.  In TradingView, open the **Pine Editor** (bottom panel).
3.  Paste the code and click **Add to Chart**.
4.  **Automatic Indicators**: If your strategy journal contains a `RUNTIME_HEADER` with `indicators` metadata (e.g., EMA, SMA, RSI, MACD), the generated script will automatically plot these indicators and add snapshots to the trade labels.

### Dashboard (real-time)

- Open `http://localhost:3000` (historical dashboard) or `http://localhost:3001` (forge dashboard).
- Go to **Journal Events** — filter by event type, symbol, or date.
- Click **Chart** to view the event on a local chart with a time marker.
- Click **TV** to open TradingView at the matching symbol and timeframe.

---

## 15. Logging And Expected Artifacts

| File | Description |
|---|---|
| `logs\strategy_runtime\runtime.log` | Timestamped runtime log |
| `logs\strategy_runtime\*_journal.jsonl` | All strategy events (orders, fills, signals) |
| `logs\strategy_runtime\nifty_trend_decisions_<date>.txt` | Human-readable decision log per bar |
| `logs\ticks\<symbol>_<date>.csv` | Tick capture output (live-paper mode) |
| `logs\run_summaries\replay_run_YYYYMMDD_HHMMSS.log` | Per-run replay preflight, progress, and final summary |
| `logs\runtime_stdout.log` | Strategy runtime stdout captured by `START_REPLAY_KIT.ps1` |
| `logs\runtime_stderr.log` | Strategy runtime stderr captured by `START_REPLAY_KIT.ps1` |
| `logs\replay_engine.log` | Replay engine stdout (via runner script) |
| `logs\replay_engine_err.log` | Replay engine stderr |

Minimum acceptance checks after a session:
- `runtime.log` has at least one strategy evaluation cycle after market open (or replay start).
- Journal contains `ORDER_PLACED` and `ORDER_FILL` events for paper trades.
- Decision log has one line per closed 1-minute bar with signal status.
- Backtest output shows trade count > 0 for days with market data.

---

## 16. Smoke Tests And Validation

Run these after deploying any kit to confirm the install is healthy.

### Environment check

```powershell
.\.venv\Scripts\python.exe -c "import trading_core; print('OK trading_core')"
.\.venv\Scripts\python.exe -c "import asyncpg; print('OK asyncpg')"
.\.venv\Scripts\python.exe -c "import pandas; print('OK pandas')"
```

### DB connectivity check

```powershell
.\.venv\Scripts\python.exe -c "
import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv('config/.env')
async def check():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    row = await conn.fetchrow('SELECT count(*) FROM master_broker.ohlcv_1m LIMIT 1')
    print('DB OK, ohlcv_1m accessible')
    await conn.close()
asyncio.run(check())
"
```

### Replay kit smoke test

```powershell
# Terminal 1
.\.venv\Scripts\python.exe .\services\replay_engine\main.py

# Terminal 2 — check WebSocket is up
.\.venv\Scripts\python.exe -c "
import asyncio, websockets
async def t():
    async with websockets.connect('ws://localhost:8765') as ws:
        print('Replay engine WebSocket OK')
asyncio.run(t())
"
```

### Backtest smoke test (quick sanity)

```powershell
.\.venv\Scripts\python.exe .\scripts\strategy_backtest.py --from 2026-04-28 --to 2026-04-28
```

Should print a (possibly empty) trade table with no errors.

### Strategy runtime API check

```powershell
curl http://localhost:8090/health
curl http://localhost:8090/status
```

---

## 17. Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Missing auth token (live-paper) | Launcher performs preflight auth check; prints login URL if token is missing |
| No option strike near Rs 200 premium | Configurable `NIFTY_PREMIUM_TOLERANCE`; strategy skips and logs reason |
| Replay data gap for a date | Backtest will return zero trades; check DB coverage with `SELECT count(*) FROM master_broker.ohlcv_1m WHERE ts::date = '2026-04-15'` |
| Replay engine exits early | Check `logs\replay_engine_err.log`; verify DB credentials in `config\.env` |
| Tick capture file import schema drift | Validate with `--dry-run` before writing; lock JSONL schema |
| Telegram bot not sending messages | Ensure `TELEGRAM_ENABLED=true` and `TELEGRAM_CHAT_ID` is set; test token at `https://api.telegram.org/bot<TOKEN>/getMe` |

---

## 18. FAQ

### Why is Ctrl+C cleanup needed in replay kit? Can't processes stop on their own?

The runtime can exit when replay completes, but the replay engine process can continue running unless explicitly stopped. `START_REPLAY_KIT.ps1` handles Ctrl+C by stopping both child processes so you do not leave orphaned background workers.

### In replay mode, are option chain/quotes still read from `master_broker.options_ohlc_1m_fromupstox`?

Yes by default. The resolver uses `master_broker.options_ohlc_1m_fromupstox` unless you override it with `STRATEGY_RUNTIME_REPLAY_OPTIONS_TABLE`. This is separate from `STRATEGY_RUNTIME_REPLAY_DATA_TYPE`, which controls replay stream data (`ohlcv_1m`, `market_ticks`, etc.).

### What does the backtest runner provide if I can run scripts directly?

`START_BACKTEST_KIT.ps1` adds convenience and guardrails: env loading (including optional strategy config), interactive date prompts, date validation, smoke-mode normalization, and consistent argument/run summaries. It now always uses the strategy-runtime offline adapter path. Direct script calls remain best for automation or custom pipelines.

### Is `Replay-paper` in `astra-kit` the same as replay kit?

Runtime behavior is the same (historical data over replay WebSocket). Packaging is different: replay kit bundles/starts replay engine; `astra-kit` requires replay engine to be started externally.

### Is there a live-live order mode (for example Zerodha orders with live data feed)?

Yes. Use a live trading provider via `STRATEGY_RUNTIME_TRADING_PROVIDER` (for example `zerodha`) while keeping your chosen live data provider in `STRATEGY_RUNTIME_PROVIDER`. Validate extensively in paper mode first.

### Is Unified Capture mode basically live-paper plus tick CSV capture? Is DB optional?

Yes. Unified Capture is live-paper strategy plus recorder orchestration in one command. DB persistence is optional (`--enable-db`), and recommended practice is CSV-first daytime capture followed by EOD DB import.

### Should `services/strategy_runtime` be part of the backtest kit?

Yes. The refactored backtest and optimizer use the strategy-runtime offline adapter path, so `services/strategy_runtime` is a required part of the backtest kit.

---

Owner: Astra runtime track
Last updated: 2026-05-11
