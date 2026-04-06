@echo off
echo Starting Data Collector Service...
:: Get project root relative to script location
set "ROOT=%~dp0.."
pushd "%ROOT%\services\data_collector"

set "PYTHONPATH=%ROOT%"
set "TRADING_CONFIG_DIR=../../config"
set "TRADING_AUTH_DIR=../../config/auth"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)
python main.py
popd
pause
