# Astra User Guide (Standalone Desktop, Paper Trading)

Version: 2026-04-30
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
9. [Configuration Reference](#9-configuration-reference)
10. [Telegram Alerts Setup](#10-telegram-alerts-setup)
11. [Journal Event Linking](#11-journal-event-linking)
12. [Logging And Expected Artifacts](#12-logging-and-expected-artifacts)
13. [Smoke Tests And Validation](#13-smoke-tests-and-validation)
14. [Risks And Mitigations](#14-risks-and-mitigations)

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
| Journal JSONL with TradingView deep-links | ✅ |
| Telegram trade alerts | ✅ |
| File-based option tick capture (EOD import) | ✅ |
| One-click kit builder script | ✅ |

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
- `scripts/backtest_nifty_trend.py` — single-run backtest
- `scripts/optimize_nifty_trend.py` — grid search optimizer
- `packages/trading_core/` — shared models
- `config/` — DB credentials env
- `docs/` — strategy documentation and this user guide

### astra-kit-v1-windows (live-paper + replay-paper)
**Use case:** Paper trade using a real-time live broker feed (Upstox/Fyers) during market hours, **or** connect to an externally running replay engine for replay-paper mode.

Contents:
- `services/strategy_runtime/` — includes the replay option data resolver and `replay_ws` feed support
- `packages/trading_core/`
- `config/` — includes `strategy_runtime.paper_replay.env.example` and `strategy_runtime.paper_live.env.example`
- `scripts/start_strategy_runtime_live_paper.ps1` — live broker feed launcher
- `scripts/start_strategy_runtime_paper_replay.ps1` — replay-paper launcher (connects to external replay engine)
- `scripts/authenticate_broker.py`, `scripts/start_upstox_tick_capture_file.ps1`

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
- `scripts/backtest_nifty_trend.py`
- `scripts/optimize_nifty_trend.py`
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
pip install asyncpg pandas python-dotenv ta-lib
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
STRATEGY_RUNTIME_QUANTITY=1
STRATEGY_RUNTIME_INITIAL_CAPITAL=100000
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
11. On Ctrl+C, cleanly shuts down both processes

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

In replay mode, option chain and quote lookups are served from `master_broker.options_ohlc_1m_fromupstox` at the simulated timestamp — no live broker is called. The resolver is automatically injected by the runtime when `FEED_SOURCE=replay_ws`.

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

Show top 15 parameter combinations instead of default 10:

```powershell
.\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28 -Mode optimize -Top 15
```

### Run scripts directly (bypass runner)

Single backtest:

```powershell
.\.venv\Scripts\python.exe .\scripts\backtest_nifty_trend.py --from 2026-04-01 --to 2026-04-28
```

Grid search optimisation:

```powershell
.\.venv\Scripts\python.exe .\scripts\optimize_nifty_trend.py --from 2026-04-01 --to 2026-04-28 --top 10
```

Custom symbol:

```powershell
.\.venv\Scripts\python.exe .\scripts\backtest_nifty_trend.py `
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
| Premium target (Rs) | `NIFTY_PREMIUM_TARGET` | 200.0 |
| Premium tolerance (Rs) | `NIFTY_PREMIUM_TOLERANCE` | 30.0 |
| Reward:risk ratio | `NIFTY_REWARD_RISK_RATIO` | 2.0 |

---

## 8. Live-Paper Kit: Paper Trading With Live Broker Feed Or External Replay

The `astra-kit` supports two operating modes:

| Mode | Feed source | Replay engine needed? |
|---|---|---|
| Live-paper | Live broker (Upstox/Fyers) | No |
| Replay-paper | Historical DB via WebSocket | Yes — started externally |

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

### Mode 2: Replay-paper (using external replay engine)

`astra-kit` does **not** bundle the replay engine. You need it running separately first — either from `astra-replay-kit` or from the workspace. Then connect this kit's strategy runtime to it.

#### Step 1: Start the replay engine (from astra-replay-kit or workspace)

From `astra-replay-kit`:
```powershell
# In astra-replay-kit folder — start engine only
.\.venv\Scripts\python.exe .\services\replay_engine\main.py
```

From workspace:
```powershell
python .\services\replay_engine\main.py
```

#### Step 2: Start strategy runtime in replay mode (from astra-kit)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_strategy_runtime_paper_replay.ps1 `
  -Strategy nifty_trend_options -StartReplayEngine:$false
```

Ensure `config\strategy_runtime.paper_replay.env` has:
```dotenv
STRATEGY_RUNTIME_FEED_SOURCE=replay_ws
STRATEGY_RUNTIME_REPLAY_WS_URL=ws://localhost:8765
STRATEGY_RUNTIME_STRATEGY=nifty_trend_options
```

> **Tip:** If you want the replay engine bundled with the strategy runtime in a single launcher, use `astra-replay-kit` instead — it bundles everything and `START_REPLAY_KIT.ps1` starts both together.

### Tick capture (EOD DB import workflow)

Start option tick capture to file during market hours:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_upstox_tick_capture_file.ps1 -StrikeCount 21 -Mode full
```

After market close, import captured ticks into DB:

```powershell
python .\scripts\lib\import_ticks_to_db.py --date 2026-04-30 --dir .\logs\ticks
```

Dry run (no writes):

```powershell
python .\scripts\lib\import_ticks_to_db.py --date 2026-04-30 --dir .\logs\ticks --dry-run
```

---

## 9. Configuration Reference

### strategy_runtime.paper_replay.env — full key list

| Key | Description | Example |
|---|---|---|
| `STRATEGY_RUNTIME_FEED_SOURCE` | `broker` or `replay_ws` | `replay_ws` |
| `STRATEGY_RUNTIME_PROVIDER` | Broker provider namespace | `fyers` |
| `STRATEGY_RUNTIME_SYMBOL` | Underlying symbol | `NSE:NIFTY50-INDEX` |
| `STRATEGY_RUNTIME_TIMEFRAME` | Bar timeframe | `1m` |
| `STRATEGY_RUNTIME_STRATEGY` | Strategy module name | `nifty_trend_options` |
| `STRATEGY_RUNTIME_QUANTITY` | Lots per trade | `1` |
| `STRATEGY_RUNTIME_INITIAL_CAPITAL` | Starting capital (Rs) | `100000` |
| `STRATEGY_RUNTIME_STOP_LOSS_PCT` | Stop loss % (0.60 = 60%) | `0.60` |
| `STRATEGY_RUNTIME_REPLAY_WS_URL` | Replay engine WebSocket URL | `ws://localhost:8765` |
| `STRATEGY_RUNTIME_REPLAY_SPEED` | Replay speed multiplier | `5` |
| `STRATEGY_RUNTIME_REPLAY_START_TIME` | ISO8601 replay start | `2026-04-15T09:15:00+05:30` |
| `STRATEGY_RUNTIME_REPLAY_END_TIME` | ISO8601 replay end | `2026-04-15T15:30:00+05:30` |
| `STRATEGY_RUNTIME_REPLAY_DATA_TYPE` | Data type streamed by replay engine | `ohlcv_1m` or `market_ticks` |
| `STRATEGY_RUNTIME_INDICATOR_INPUT_MODE` | How indicators receive data | `bars_1m` or `ticks` |
| `TELEGRAM_ENABLED` | Enable Telegram alerts | `false` |}
| `NIFTY_PREMIUM_TARGET` | Target option premium (Rs) | `200.0` |
| `NIFTY_PREMIUM_TOLERANCE` | Premium tolerance window (Rs) | `30.0` |
| `NIFTY_REWARD_RISK_RATIO` | Exit target as multiple of stop | `2.0` |
| `NIFTY_EMA_PERIOD` | EMA period for trend | `20` |
| `NIFTY_SMA_PERIOD` | SMA period for trend | `20` |
| `NIFTY_MACD_FAST` | MACD fast EMA | `12` |
| `NIFTY_MACD_SLOW` | MACD slow EMA | `26` |
| `NIFTY_MACD_SIGNAL` | MACD signal line | `9` |

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
| `TELEGRAM_CHAT_ID` | Your chat ID (see Section 10) |

---

## 10. Telegram Alerts Setup

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

## 11. Journal Event Linking

Every order and signal decision is written to a JSONL journal at:

```
logs\strategy_runtime\*_journal.jsonl
```

### Dashboard (real-time)

- Open `http://localhost:3000` (historical dashboard) or `http://localhost:3001` (forge dashboard).
- Go to **Journal Events** — filter by event type, symbol, or date.
- Click **Chart** to view the event on a local chart with a time marker.
- Click **TV** to open TradingView at the matching symbol and timeframe.

### Offline report generation

```powershell
python .\UtilTools\journal_event_linker.py `
  --journal .\logs\strategy_runtime\runtime_journal.jsonl `
  --output-md .\logs\strategy_runtime\journal_report.md `
  --output-json .\logs\strategy_runtime\journal_report.json
```

Filter to fills only:

```powershell
python .\UtilTools\journal_event_linker.py `
  --journal .\logs\strategy_runtime\runtime_journal.jsonl `
  --event ORDER_FILL --limit 500
```

### TradingView symbol map

`config\strategies\tradingview_symbol_map.json`:

```json
{
  "NIFTY": "NSE:NIFTY",
  "BANKNIFTY": "NSE:BANKNIFTY"
}
```

NIFTY option symbols (e.g., `NIFTY24APR26000CE`) are auto-converted to TradingView NFO format.

---

## 12. Logging And Expected Artifacts

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

## 13. Smoke Tests And Validation

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
.\.venv\Scripts\python.exe .\scripts\backtest_nifty_trend.py --from 2026-04-28 --to 2026-04-28
```

Should print a (possibly empty) trade table with no errors.

### Strategy runtime API check

```powershell
curl http://localhost:8090/health
curl http://localhost:8090/status
```

---

## 14. Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Missing auth token (live-paper) | Launcher performs preflight auth check; prints login URL if token is missing |
| No option strike near Rs 200 premium | Configurable `NIFTY_PREMIUM_TOLERANCE`; strategy skips and logs reason |
| Replay data gap for a date | Backtest will return zero trades; check DB coverage with `SELECT count(*) FROM master_broker.ohlcv_1m WHERE ts::date = '2026-04-15'` |
| Replay engine exits early | Check `logs\replay_engine_err.log`; verify DB credentials in `config\.env` |
| Tick capture file import schema drift | Validate with `--dry-run` before writing; lock JSONL schema |
| Telegram bot not sending messages | Ensure `TELEGRAM_ENABLED=true` and `TELEGRAM_CHAT_ID` is set; test token at `https://api.telegram.org/bot<TOKEN>/getMe` |

---

Owner: Astra runtime track
Last updated: 2026-04-30
