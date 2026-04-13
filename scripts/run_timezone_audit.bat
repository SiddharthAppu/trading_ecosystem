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
    echo Running timezone audit with defaults...
    "%PYTHON_EXE%" "%ROOT%\scripts\lib\audit_timezone_integrity.py" --provider all
) else (
    "%PYTHON_EXE%" "%ROOT%\scripts\lib\audit_timezone_integrity.py" %*
)

endlocal
