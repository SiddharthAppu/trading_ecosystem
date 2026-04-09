@echo off
echo Starting Execution Engine Service...
:: Get project root relative to script location
set "ROOT=%~dp0.."
pushd "%ROOT%\services\execution_engine"

set "PYTHONPATH=%ROOT%"
set "TRADING_CONFIG_DIR=../../config"
set "TRADING_AUTH_DIR=../../config/auth"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Missing service virtual environment at services\execution_engine\.venv
    popd
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
popd
pause
