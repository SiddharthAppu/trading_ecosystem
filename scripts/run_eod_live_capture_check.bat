@echo off
setlocal

set "ROOT=%~dp0.."
pushd "%ROOT%"

set "PYTHONPATH=%ROOT%"
set "TRADING_CONFIG_DIR=config"
set "TRADING_AUTH_DIR=config/auth"

if not exist "services\data_collector\.venv\Scripts\python.exe" (
    echo ERROR: Missing service virtual environment at services\data_collector\.venv
    popd
    pause
    exit /b 1
)

"services\data_collector\.venv\Scripts\python.exe" scripts\verify_eod_live_capture.py %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo EOD live capture check passed.
) else (
    echo EOD live capture check failed with exit code %EXIT_CODE%.
)

popd
pause
exit /b %EXIT_CODE%