@echo off
echo Starting Replay Engine Service...
:: Get project root relative to script location
set "ROOT=%~dp0.."

call :is_port_listening 8765
if %ERRORLEVEL%==0 (
    echo [*] Replay Engine already listening on port 8765. Reusing existing process.
    exit /b 0
)

pushd "%ROOT%\services\replay_engine"

set "PYTHONPATH=%ROOT%"
set "TRADING_CONFIG_DIR=../../config"
set "TRADING_AUTH_DIR=../../config/auth"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Missing service virtual environment at services\replay_engine\.venv
    popd
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
popd
pause
exit /b 0

:is_port_listening
powershell -NoProfile -Command "$port = %~1; if (@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).Count -gt 0) { exit 0 } else { exit 1 }"
exit /b %ERRORLEVEL%
