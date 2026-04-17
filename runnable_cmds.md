# 🚀 Runnable Commands

This document lists all the major commands needed for local development, setup, and maintenance.

## 🛠️ Master Startup
Run this script at the root to start all core services in separate terminal windows.
```powershell
.\start_platform.bat
```

Show command help and all startup modes:
```powershell
.\start_platform.bat --help
```

Open services in a single Windows Terminal window with tabs (instead of separate CMD windows):
```powershell
.\start_platform.bat --wt
# or combine with a mode
.\start_platform.bat replay-studio --wt
```

### Startup Modes Explained

1. `all` (default)
```powershell
.\start_platform.bat
# or
.\start_platform.bat all
```
What it starts: TimescaleDB + Data Collector + Replay Engine + Execution Engine + Historical UI + Forge UI.
Best for: full local platform validation and end-to-end debugging.

2. `collector`
```powershell
.\start_platform.bat collector
```
What it starts: TimescaleDB + Data Collector only.
Best for: live market ingestion, auth checks, recorder workflows, and data API-only tasks.

3. `replay`
```powershell
.\start_platform.bat replay
```
What it starts: TimescaleDB + Replay Engine only.
Best for: replay backend testing without dashboards or live collector.

4. `execution`
```powershell
.\start_platform.bat execution
```
What it starts: TimescaleDB + Execution Engine only.
Best for: strategy orchestration debugging in isolation.

5. `uis-only`
```powershell
.\start_platform.bat uis-only
```
What it starts: Historical UI + Forge UI only.
Best for: frontend work when backend services are already running elsewhere.

6. `collector+replay`
```powershell
.\start_platform.bat collector+replay
```
What it starts: TimescaleDB + Data Collector + Replay Engine.
Best for: combined live capture and replay backend workflows.

7. `replay-studio` (alias: `historical+replay`)
```powershell
.\start_platform.bat replay-studio
```
What it starts: TimescaleDB + Replay Engine + Historical UI.
Best for: replay study sessions in Historical Dashboard while keeping live collector optional.

8. `status`
```powershell
.\start_platform.bat status
```
What it shows: per-service running state, bound port, PID, process name, and executable path. Also reports TimescaleDB container health.
Best for: quickly checking what is running before starting additional workflows or investigating port conflicts.

Note: startup scripts skip duplicate launches if required ports are already occupied.

## 🏗️ Local Environment Setup

### 🔄 Configuration Sync
Before starting, propagate the root `.env` to all apps:
```powershell
.\scripts\sync_env.bat
```

### Python Environment
Most services use Python. It's recommended to use virtual environments.
```powershell
# In services/data_collector or services/replay_engine or services/execution_engine
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Shared Package Link
To work with `trading_core` as a package, you MUST install it in editable mode in each service:
```powershell
# In each of services/data_collector, services/replay_engine, services/execution_engine
.\.venv\Scripts\activate
pip install -e ..\..\packages\trading_core
```

### UI Apps Setup (Next.js)
```powershell
cd apps\historical_dashboard
npm install
npm run dev

cd apps\forge_dashboard
npm install
npm run dev
```

## 🧰 Utility Scripts (CLI)
These scripts are located in `scripts/` and can be run individually using any service's venv.

### 🔐 Authentication Verification & Login
Check if your broker sessions are active and generate new login links.
```powershell
# 1. Check current status
.\services\data_collector\.venv\Scripts\python.exe scripts\verify_auth.py

# 2. Login & Save Session (New!)
# Usage: --provider <fyers|upstox>
.\services\data_collector\.venv\Scripts\python.exe scripts\authenticate.py --provider fyers
```
*   **Step 1:** Visit the generated URL in your browser.
*   **Step 2:** Log in and copy the entire `127.0.0.1` redirect URL from the address bar.
*   **Step 3:** Paste it back into the terminal to save your token.

### 📥 Quick OHLC Download
Headless downloader for index or stock historical data.
```powershell
# Usage: --symbol <SYM> --start <YYYY-MM-DD> --end <YYYY-MM-DD> [--provider <fyers|upstox>]
.\services\data_collector\.venv\Scripts\python.exe scripts\quick_download.py --symbol "NSE:NIFTY50-INDEX" --start 2026-03-01 --end 2026-03-07
```

### 🧬 Quick Option Chain
Discovers and downloads an entire option chain for a specific expiry.
```powershell
# Usage: --underlying <SYM> --expiry <EXPIRY> --start <YYYY-MM-DD> --end <YYYY-MM-DD>
.\services\data_collector\.venv\Scripts\python.exe scripts\quick_option_chain.py --underlying "NSE:NIFTY50-INDEX" --expiry "26MAR" --start 2026-03-24 --end 2026-03-24
```

### 📅 Expiry Discovery (Single/Both Providers)
Fetch available expiries from the unified Data Collector endpoint.
```powershell
# Both providers
.\services\data_collector\.venv\Scripts\python.exe scripts\list_expiries.py

# One provider
.\services\data_collector\.venv\Scripts\python.exe scripts\list_expiries.py --provider upstox
.\services\data_collector\.venv\Scripts\python.exe scripts\list_expiries.py --provider fyers
```

### 📡 Live Recorder (Single Worker)
Run one provider + one expiry recorder in non-interactive mode.
```powershell
.\services\data_collector\.venv\Scripts\python.exe scripts\quick_live_recorder.py --provider upstox --expiry 2026-04-14 --strike-count 21 --mode full --non-interactive
.\services\data_collector\.venv\Scripts\python.exe scripts\quick_live_recorder.py --provider fyers --expiry 2026-04-14 --strike-count 21 --mode lite --non-interactive
```

### 🧠 Master Recorder (2 Workers)
Launch next 4 Tuesday expiries across both providers (1 worker per provider, each handling all expiries).
```powershell
.\services\data_collector\.venv\Scripts\python.exe scripts\master_recorder.py --strike-count 21 --heartbeat-seconds 20
```

### ✅ End-Of-Day Live Capture Verification
Run a pass/fail health check after market close for the day's live tick and Greeks capture.
```powershell
.\services\data_collector\.venv\Scripts\python.exe scripts\verify_eod_live_capture.py

# double-clickable batch wrapper
.\scripts\run_eod_live_capture_check.bat

# explicit date or custom thresholds
.\services\data_collector\.venv\Scripts\python.exe scripts\verify_eod_live_capture.py --date 2026-04-09 --min-fyers-symbols 150 --max-upstox-symbol-drift 15
```

The script also writes a dated log file under `logs\eod_live_capture\` on every run.

### 🗂️ DB Greeks + Compression Migration
Apply schema update script for Greeks columns and Timescale compression settings.
```powershell
psql -h localhost -U trading -d trading_db -f scripts\add_greeks_and_compression.sql
```

### 🌙 End-Of-Day Greeks Merge (Provider -> Master)
Merge `broker_upstox.options_greeks_live` and `broker_fyers.options_greeks_live` into `analytics.options_greeks_master`.
```powershell
# default: previous IST day
.\services\data_collector\.venv\Scripts\python.exe scripts\merge_provider_greeks_to_master.py

# explicit day
.\services\data_collector\.venv\Scripts\python.exe scripts\merge_provider_greeks_to_master.py --date 2026-04-08
```

### 🗄️ Database Management
TimescaleDB must be explicitly managed to prevent freezes and ensure continuity. The `db_data/` and `db_backups/` folders are heavily git-ignored to prevent pushing massive datasets to cloud hosting.

**1. Initialize DB / Safe Setup**  
Initialize all tables and correct unique indexing logic (safe to run over existing data).
```powershell
.\services\data_collector\.venv\Scripts\python.exe scripts\setup_db.py
```

**2. Continuity Gap Scanner**  
Verifies if you have any missing calendar days or data leaks inside your downloaded charts.
```powershell
.\services\data_collector\.venv\Scripts\python.exe scripts\verify_db_gaps.py
```

**3. Snapshot Backup & Version Control**  
Uses Docker natively to securely backup your full database into version-controlled `.sql` files without stopping your environment. Automatically purges old backups past limit.
```powershell
.\services\data_collector\.venv\Scripts\python.exe scripts\db_backup.py --max 30
```

**4. Nuclear Reset**  
Drops all trading and option schemas permanently and rebuilds them. (WARNING: Wipes all historical data!)
```powershell
.\services\data_collector\.venv\Scripts\python.exe scripts\reset_db.py
```

## 📶 Service Management
...
