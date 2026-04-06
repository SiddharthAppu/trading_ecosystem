@echo off
setlocal

:: Get the root directory (one level up from the scripts folder)
set "ROOT_DIR=%~dp0.."
pushd "%ROOT_DIR%"

echo === 🚀 UNIFIED TRADING ECOSYSTEM MASTER SETUP ===

:: 1. Sync Configuration
echo [1/4] Syncing environment variables...
call scripts\sync_env.bat

:: 2. Setup Shared Python Package
echo [2/4] Initializing shared core package...
pushd packages\trading_core
python -m pip install -e .
popd

:: 3. Setup Backend Services
set SERVICES=data_collector replay_engine execution_engine
for %%s in (%SERVICES%) do (
    echo [*] Setting up service: %%s...
    if not exist "services\%%s\.venv" (
        echo Creating virtual environment for %%s...
        python -m venv services\%%s\.venv
    )
    echo Installing dependencies for %%s...
    :: Activate and install requirements plus the local core link
    pushd services\%%s
    call .venv\Scripts\activate.bat
    pip install -e ..\..\packages\trading_core
    if exist "requirements.txt" (
        pip install -r requirements.txt
    )
    popd
)

:: 4. Setup Frontend Apps
set APPS=historical_dashboard forge_dashboard
for %%a in (%APPS%) do (
    echo [*] Setting up UI app: %%a...
    if exist "apps\%%a" (
        pushd apps\%%a
        if not exist "node_modules" (
            echo Running npm install for %%a...
            npm install
        ) else (
            echo node_modules already exists for %%a, skipping install.
        )
        popd
    ) else (
        echo [WARNING] App directory apps\%%a not found.
    )
)

echo.
echo === ✅ SETUP COMPLETE! ===
echo You can now use start_platform.bat to run the ecosystem.
popd
pause
