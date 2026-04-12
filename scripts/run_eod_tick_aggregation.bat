@echo off
setlocal

set "ROOT=%~dp0.."
set "PYTHONPATH=%ROOT%"
set "TRADING_CONFIG_DIR=%ROOT%\config"
set "TRADING_AUTH_DIR=%ROOT%\config\auth"

set "PYTHON_EXE=%ROOT%\services\data_collector\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo ERROR: Missing virtual environment at services\data_collector\.venv
    exit /b 1
)

if "%~1"=="" (
    for /f %%d in ('powershell -NoProfile -Command "$ist=[System.TimeZoneInfo]::FindSystemTimeZoneById('India Standard Time'); [System.TimeZoneInfo]::ConvertTimeFromUtc((Get-Date).ToUniversalTime(),$ist).AddDays(-1).ToString('yyyy-MM-dd')"') do set TARGET_DATE=%%d
    echo No --date supplied. Defaulting to yesterday IST: %TARGET_DATE%
    "%PYTHON_EXE%" "%ROOT%\scripts\aggregate_ticks_to_1min.py" --provider all --date %TARGET_DATE%
) else (
    "%PYTHON_EXE%" "%ROOT%\scripts\aggregate_ticks_to_1min.py" %*
)

endlocal
