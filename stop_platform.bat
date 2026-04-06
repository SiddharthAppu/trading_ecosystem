@echo off
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

:: Also target generic node/python as a fallback if window title logic fails
:: (Optional, but let's keep it safe to only target our titles first)

echo.
echo ========================================
echo   All ecosystem processes terminated!
echo ========================================
pause
