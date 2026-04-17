@echo off
setlocal

:: Get the root directory (one level up from the scripts folder)
set "ROOT_DIR=%~dp0.."
pushd "%ROOT_DIR%"

set "PYTHON_CMD="
where py >nul 2>&1
if %ERRORLEVEL%==0 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if %ERRORLEVEL%==0 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo [ERROR] Python not found in PATH. Install Python 3 or ensure 'py' or 'python' is available.
    popd
    exit /b 1
)

echo === 🚀 UNIFIED TRADING ECOSYSTEM MASTER SETUP ===

:: 1. Sync Configuration
echo [1/4] Syncing environment variables...
call scripts\sync_env.bat

:: 2. Setup Shared Python Package
echo [2/4] Initializing shared core package...
pushd packages\trading_core
%PYTHON_CMD% -m pip install -e .
popd

:: 3. Setup Backend Services
set SERVICES=data_collector replay_engine execution_engine
for %%s in (%SERVICES%) do (
    echo [*] Setting up service: %%s...
    if not exist "services\%%s\.venv" (
        echo Creating virtual environment for %%s...
        %PYTHON_CMD% -m venv services\%%s\.venv
    )
    echo Installing dependencies for %%s...
    :: Install via service venv interpreter to avoid shell activation inconsistencies.
    pushd services\%%s
    .venv\Scripts\python.exe -m pip install -e ..\..\packages\trading_core
    if exist "requirements.txt" (
        .venv\Scripts\python.exe -m pip install -r requirements.txt
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
