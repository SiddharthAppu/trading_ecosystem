@echo off
setlocal
set "ROOT_DIR=%~dp0"
pushd "%ROOT_DIR%"

set "PYTHONPATH=%ROOT_DIR%"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=all"

if /I "%MODE%"=="all" goto :run_all
if /I "%MODE%"=="collector" goto :run_collector
if /I "%MODE%"=="replay" goto :run_replay
if /I "%MODE%"=="execution" goto :run_execution
if /I "%MODE%"=="uis-only" goto :run_uis_only
if /I "%MODE%"=="collector+replay" goto :run_collector_replay
if /I "%MODE%"=="replay-studio" goto :run_replay_studio
if /I "%MODE%"=="historical+replay" goto :run_replay_studio

echo Invalid mode: %MODE%
echo.
echo Usage:
echo   start_platform.bat [all^|collector^|replay^|execution^|uis-only^|collector+replay^|replay-studio]
echo.
popd
exit /b 1

:start_collector
start "DATA COLLECTOR" cmd /k "set ""PYTHONPATH=%ROOT_DIR%"" && call scripts\start_collector_service.bat"
goto :eof

:start_replay
start "REPLAY ENGINE" cmd /k "call scripts\start_replay_service.bat"
goto :eof

:start_execution
start "EXECUTION ENGINE" cmd /k "call scripts\start_execution_service.bat"
goto :eof

:start_historical_ui
start "HISTORICAL UI" cmd /k "set PORT=3000 && pushd apps\historical_dashboard && npm run dev"
goto :eof

:start_forge_ui
start "FORGE UI" cmd /k "set PORT=3001 && pushd apps\forge_dashboard && npm run dev"
goto :eof

:ensure_db
echo [*] Checking Database Container (TimescaleDB)...
docker-compose up -d
echo.
goto :eof

:run_all

echo ========================================
echo   UNIFIED TRADING PLATFORM - START ALL
echo ========================================

echo.
call :ensure_db

:: 1. Start APIs and Backend Services
call :start_collector
call :start_replay
call :start_execution

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

:run_execution
echo ========================================
echo   UNIFIED TRADING PLATFORM - START EXECUTION
echo ========================================
echo.
call :ensure_db
call :start_execution
echo Launch complete: Execution Engine + DB
goto :done

:run_uis_only
echo ========================================
echo   UNIFIED TRADING PLATFORM - START UIs ONLY
echo ========================================
echo.
call :start_historical_ui
call :start_forge_ui
echo Launch complete: Historical UI + Forge UI
goto :done

:run_collector_replay
echo ========================================
echo   UNIFIED TRADING PLATFORM - START COLLECTOR+REPLAY
echo ========================================
echo.
call :ensure_db
call :start_collector
call :start_replay
echo Launch complete: Data Collector + Replay Engine + DB
goto :done

:run_replay_studio
echo ========================================
echo   UNIFIED TRADING PLATFORM - START REPLAY STUDIO
echo ========================================
echo.
call :ensure_db
call :start_collector
call :start_replay
call :start_historical_ui
echo Launch complete: Historical UI + Data Collector + Replay Engine + DB
goto :done

:done

popd
pause
