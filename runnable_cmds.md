# 🚀 Runnable Commands

This document lists all the major commands needed for local development, setup, and maintenance.

## 🛠️ Master Startup
Run this script at the root to start all core services in separate terminal windows.
```powershell
.\start_platform.bat
```

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
.\services\data_collector\.venv\Scripts\python.exe scripts\db_backup.py --max 5
```

**4. Nuclear Reset**  
Drops all trading and option schemas permanently and rebuilds them. (WARNING: Wipes all historical data!)
```powershell
.\services\data_collector\.venv\Scripts\python.exe scripts\reset_db.py
```

## 📶 Service Management
...
