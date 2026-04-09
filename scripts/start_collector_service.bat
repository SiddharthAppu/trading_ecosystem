@echo off
echo Starting Data Collector Service...
:: Get project root relative to script location
set "ROOT=%~dp0.."
pushd "%ROOT%\services\data_collector"

set "PYTHONPATH=%ROOT%"
set "TRADING_CONFIG_DIR=../../config"
set "TRADING_AUTH_DIR=../../config/auth"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Missing service virtual environment at services\data_collector\.venv
    popd
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
popd
pause
