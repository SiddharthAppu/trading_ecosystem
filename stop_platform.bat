@echo off
setlocal EnableExtensions
set "MODE=%~1"
if "%MODE%"=="" set "MODE=all"

if /I "%MODE%"=="all" goto :stop_all
if /I "%MODE%"=="collector" goto :stop_collector
if /I "%MODE%"=="replay" goto :stop_replay
if /I "%MODE%"=="execution" goto :stop_execution
if /I "%MODE%"=="uis-only" goto :stop_uis_only
if /I "%MODE%"=="collector+replay" goto :stop_collector_replay

echo Invalid mode: %MODE%
echo.
echo Usage:
echo   stop_platform.bat [all^|collector^|replay^|execution^|uis-only^|collector+replay]
echo.
exit /b 1

:stop_all
echo ========================================
echo   UNIFIED TRADING PLATFORM - STOP ALL
echo ========================================

echo [1/5] Stopping Data Collector...
taskkill /FI "WINDOWTITLE eq DATA COLLECTOR*" /T /F >nul 2>&1

echo [2/5] Stopping Replay Engine...
taskkill /FI "WINDOWTITLE eq REPLAY ENGINE*" /T /F >nul 2>&1

echo [3/5] Stopping Execution Engine...
taskkill /FI "WINDOWTITLE eq EXECUTION ENGINE*" /T /F >nul 2>&1

echo [4/5] Stopping Historical UI...
taskkill /FI "WINDOWTITLE eq HISTORICAL UI*" /T /F >nul 2>&1

echo [5/5] Stopping Forge UI...
taskkill /FI "WINDOWTITLE eq FORGE UI*" /T /F >nul 2>&1

echo.
echo ========================================
echo   All ecosystem processes terminated!
echo ========================================
goto :done

:stop_collector
echo ========================================
echo   UNIFIED TRADING PLATFORM - STOP COLLECTOR
echo ========================================
taskkill /FI "WINDOWTITLE eq DATA COLLECTOR*" /T /F >nul 2>&1
echo Collector process terminated.
goto :done

:stop_replay
echo ========================================
echo   UNIFIED TRADING PLATFORM - STOP REPLAY
echo ========================================
taskkill /FI "WINDOWTITLE eq REPLAY ENGINE*" /T /F >nul 2>&1
echo Replay process terminated.
goto :done

:stop_execution
echo ========================================
echo   UNIFIED TRADING PLATFORM - STOP EXECUTION
echo ========================================
taskkill /FI "WINDOWTITLE eq EXECUTION ENGINE*" /T /F >nul 2>&1
echo Execution process terminated.
goto :done

:stop_uis_only
echo ========================================
echo   UNIFIED TRADING PLATFORM - STOP UIs ONLY
echo ========================================
taskkill /FI "WINDOWTITLE eq HISTORICAL UI*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq FORGE UI*" /T /F >nul 2>&1
echo UI processes terminated.
goto :done

:stop_collector_replay
echo ========================================
echo   UNIFIED TRADING PLATFORM - STOP COLLECTOR+REPLAY
echo ========================================
taskkill /FI "WINDOWTITLE eq DATA COLLECTOR*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq REPLAY ENGINE*" /T /F >nul 2>&1
echo Collector and replay processes terminated.
goto :done

:done
pause
endlocal
