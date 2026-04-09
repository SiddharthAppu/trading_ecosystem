@echo off
setlocal
set "ROOT_DIR=%~dp0"
pushd "%ROOT_DIR%"

set "PYTHONPATH=%ROOT_DIR%"

echo ========================================
echo   UNIFIED TRADING PLATFORM - START ALL
echo ========================================

echo.
echo [*] Checking Database Container (TimescaleDB)...
docker-compose up -d
echo.

:: 1. Start APIs and Backend Services
start "DATA COLLECTOR" cmd /k "set ""PYTHONPATH=%ROOT_DIR%"" && call scripts\start_collector_service.bat"
start "REPLAY ENGINE" cmd /k "call scripts\start_replay_service.bat"
start "EXECUTION ENGINE" cmd /k "call scripts\start_execution_service.bat"

:: 2. Start Dashboards (Explicit Ports)
start "HISTORICAL UI" cmd /k "set PORT=3000 && pushd apps\historical_dashboard && npm run dev"
start "FORGE UI" cmd /k "set PORT=3001 && pushd apps\forge_dashboard && npm run dev"

echo.
echo ========================================
echo   Ecosystem launch sequence triggered!
echo ========================================
echo  - Historical UI:  http://localhost:3000
echo  - Strategy Forge: http://localhost:3001
echo  - API Backend:    http://localhost:8080
echo ========================================

popd
pause
