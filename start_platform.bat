@echo off
setlocal EnableDelayedExpansion
set "ROOT_DIR=%~dp0"
pushd "%ROOT_DIR%"

set "PYTHONPATH=%ROOT_DIR%"
set "TRADING_CONFIG_DIR=%ROOT_DIR%config"
set "TRADING_AUTH_DIR=%ROOT_DIR%config\auth"
set "USE_WT=0"
set "MODE=%~1"

if /I "%~1"=="--wt" (
    set "USE_WT=1"
    set "MODE=all"
)
if /I "%~2"=="--wt" (
    set "USE_WT=1"
)

if "%MODE%"=="" set "MODE=all"

if /I "%MODE%"=="--help" goto :print_usage
if /I "%MODE%"=="-h" goto :print_usage
if /I "%MODE%"=="/?" goto :print_usage
if /I "%MODE%"=="status" goto :run_status

if "%USE_WT%"=="1" (
    where wt >nul 2>&1
    if not %ERRORLEVEL%==0 (
        echo [!] Windows Terminal not found. Falling back to separate CMD windows.
        set "USE_WT=0"
    )
)

if /I "%MODE%"=="all" goto :run_all
if /I "%MODE%"=="collector" goto :run_collector
if /I "%MODE%"=="replay" goto :run_replay
if /I "%MODE%"=="uis-only" goto :run_uis_only
if /I "%MODE%"=="collector+replay" goto :run_collector_replay
if /I "%MODE%"=="replay-studio" goto :run_replay_studio
if /I "%MODE%"=="historical+replay" goto :run_replay_studio

echo Invalid mode: %MODE%
echo.
goto :print_usage_error

:print_usage
echo Usage:
echo   start_platform.bat [all^|collector^|replay^|uis-only^|collector+replay^|replay-studio] [--wt]
echo   start_platform.bat --wt
echo.
echo Modes:
echo   all               - Start full stack: DB + collector + replay + execution + both UIs.
echo   collector         - Start DB + data collector only.
echo   replay            - Start DB + replay engine only.
echo   uis-only          - Start historical dashboard + forge dashboard only.
echo   collector+replay  - Start DB + data collector + replay engine.
echo   replay-studio     - Start DB + data collector + replay engine + historical dashboard.
echo   status            - Show running services, ports, PIDs and process names.
echo.
echo Notes:
echo   historical+replay is supported as an alias of replay-studio.
echo   If a port is already in use, duplicate service launch is skipped.
echo   Use --wt to open services as tabs in one Windows Terminal window.
echo.
popd
exit /b 0

:print_usage_error
echo Usage:
echo   start_platform.bat [all^|collector^|replay^|uis-only^|collector+replay^|replay-studio^|status] [--wt]
echo   start_platform.bat --wt
echo.
popd
exit /b 1

:start_collector
call :is_port_listening 8080
if %ERRORLEVEL%==0 (
    echo [*] Data Collector already listening on port 8080. Skipping duplicate launch.
    exit /b 0
)
call :launch_cmd "DATA COLLECTOR" "cd /d %ROOT_DIR%\services\data_collector && .\.venv\Scripts\python.exe main.py"
exit /b 0

:start_replay
call :is_port_listening 8765
if %ERRORLEVEL%==0 (
    echo [*] Replay Engine already listening on port 8765. Skipping duplicate launch.
    exit /b 0
)
call :launch_cmd "REPLAY ENGINE" "cd /d %ROOT_DIR%\services\replay_engine && .\.venv\Scripts\python.exe main.py"
exit /b 0


:start_historical_ui
call :is_port_listening 3000
if %ERRORLEVEL%==0 (
    echo [*] Historical UI already listening on port 3000. Skipping duplicate launch.
    exit /b 0
)
call :launch_cmd "HISTORICAL UI" "cd /d %ROOT_DIR%\apps\historical_dashboard && npm run dev"
exit /b 0

:start_forge_ui
call :is_port_listening 3001
if %ERRORLEVEL%==0 (
    echo [*] Forge UI already listening on port 3001. Skipping duplicate launch.
    exit /b 0
)
call :launch_cmd "FORGE UI" "cd /d %ROOT_DIR%\apps\forge_dashboard && npm run dev"
exit /b 0

:launch_cmd
setlocal enabledelayedexpansion
set "TITLE=%~1"
set "CMD=%~2"

if "%USE_WT%"=="1" (
    wt -w 0 new-tab --title !TITLE! cmd /k "!CMD! && pause"
) else (
    start "!TITLE!" cmd /k "!CMD! && pause"
)

endlocal
goto :eof

:ensure_db
echo [*] Checking Database Container (TimescaleDB)...
docker-compose up -d timescaledb
for /L %%I in (1,1,30) do (
	for /f "delims=" %%S in ('docker inspect -f "{{.State.Health.Status}}" trading_timescaledb 2^>nul') do set "DB_HEALTH=%%S"
	if /I "!DB_HEALTH!"=="healthy" (
		echo [*] TimescaleDB is healthy.
		echo.
		goto :eof
	)
	if /I "!DB_HEALTH!"=="starting" (
		echo [*] Waiting for TimescaleDB health... attempt %%I/30
	) else (
		if defined DB_HEALTH (
			echo [*] TimescaleDB health is !DB_HEALTH!. Waiting... attempt %%I/30
		) else (
			echo [*] Waiting for TimescaleDB container details... attempt %%I/30
		)
	)
	timeout /t 2 /nobreak >nul
)
echo [!] TimescaleDB did not report healthy within the expected time window.
echo.
goto :eof

:is_port_listening
powershell -NoProfile -Command "$port = %~1; if (@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).Count -gt 0) { exit 0 } else { exit 1 }"
exit /b %ERRORLEVEL%

:run_all

echo ========================================
echo   UNIFIED TRADING PLATFORM - START ALL
echo ========================================

echo.
call :ensure_db

:: 1. Start APIs and Backend Services
call :start_collector
call :start_replay

:: 2. Start Dashboards (Explicit Ports)
call :start_historical_ui
call :start_forge_ui

echo.
echo ========================================
echo   Ecosystem launch sequence triggered!
echo ========================================
echo  - Historical UI:  http://localhost:3000
echo  - Strategy Forge: http://localhost:3001
echo  - API Backend:    http://localhost:8080
echo ========================================

goto :done

:run_collector
echo ========================================
echo   UNIFIED TRADING PLATFORM - START COLLECTOR
echo ========================================
echo.
call :ensure_db
call :start_collector
echo Launch complete: Data Collector + DB
goto :done

:run_replay
echo ========================================
echo   UNIFIED TRADING PLATFORM - START REPLAY
echo ========================================
echo.
call :ensure_db
call :start_replay
echo Launch complete: Replay Engine + DB
goto :done

