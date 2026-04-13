@echo off
:: Thin launcher — all logic lives in run_daily_capture_eod_workflow.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_daily_capture_eod_workflow.ps1" %*
exit /b %ERRORLEVEL%

:: ---- original bat preserved below (not executed) ----
goto :eof
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0.."
set "PYTHONPATH=%ROOT%"
set "TRADING_CONFIG_DIR=%ROOT%\config"
set "TRADING_AUTH_DIR=%ROOT%\config\auth"

set "PYTHON_EXE=%ROOT%\services\data_collector\.venv\Scripts\python.exe"
set "COLLECTOR_DIR=%ROOT%\services\data_collector"
set "LIB_DIR=%ROOT%\scripts\lib"
set "LOG_DIR=%ROOT%\logs\daily_capture"

if not exist "%PYTHON_EXE%" (
    echo ERROR: Missing virtual environment at services\data_collector\.venv
    exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

call :get_ist_date
set "TRADE_DATE=%IST_DATE%"
call :get_timestamp
set "RUN_STAMP=%TS%"

echo ================================================================
echo DAILY LIVE CAPTURE + EOD PIPELINE
echo IST Trade Date: %TRADE_DATE%
echo Run Stamp: %RUN_STAMP%
echo ================================================================

set "COLLECTOR_OUT=%LOG_DIR%\collector_%RUN_STAMP%.out.log"
set "COLLECTOR_ERR=%LOG_DIR%\collector_%RUN_STAMP%.err.log"
set "RECORDER_OUT=%LOG_DIR%\master_recorder_%RUN_STAMP%.out.log"
set "RECORDER_ERR=%LOG_DIR%\master_recorder_%RUN_STAMP%.err.log"

echo [1/7] Starting Data Collector service...
for /f %%p in ('powershell -NoProfile -Command "$p=Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList 'main.py' -WorkingDirectory '%COLLECTOR_DIR%' -RedirectStandardOutput '%COLLECTOR_OUT%' -RedirectStandardError '%COLLECTOR_ERR%' -WindowStyle Hidden -PassThru; $p.Id"') do set "COLLECTOR_PID=%%p"
if "%COLLECTOR_PID%"=="" (
    echo ERROR: Could not start Data Collector.
    exit /b 1
)
echo [OK] Data Collector started with PID %COLLECTOR_PID%. Waiting 8 seconds for FastAPI startup...
timeout /t 8 /nobreak >nul
powershell -NoProfile -Command "try { $r=(Invoke-WebRequest -UseBasicParsing 'http://localhost:8080/health' -TimeoutSec 5 -ErrorAction Stop).StatusCode; Write-Host '[OK] Data Collector responding (HTTP '$r').' } catch { Write-Host '[WARN] No response yet on port 8080 - check %COLLECTOR_OUT% if issues persist.' }"

echo.
echo [2/7] Manual authentication gate.
echo You can complete any required Fyers/Upstox authentication now.
echo Current auth status:
"%PYTHON_EXE%" "%LIB_DIR%\verify_auth.py"
echo.
pause

call :get_ist_hhmm
if !IST_HHMM! GEQ 1545 (
    echo [INFO] Current IST time is already after 15:45. Skipping capture window.
    goto POST_MARKET
)

if !IST_HHMM! LSS 0900 (
    echo [3/7] Waiting until 09:00 IST to start capture...
    :WAIT_FOR_9AM
    call :get_ist_hhmm
    call :get_ist_clock
    if !IST_HHMM! GEQ 0900 goto START_CAPTURE
    echo   IST now !IST_CLOCK! - still waiting for 09:00...
    timeout /t 30 /nobreak >nul
    goto WAIT_FOR_9AM
)

:START_CAPTURE
call :get_ist_clock
echo [3/7] Starting capture workers at IST !IST_CLOCK!...
for /f %%p in ('powershell -NoProfile -Command "$p=Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList @('%LIB_DIR%\master_recorder.py','--python','%PYTHON_EXE%') -WorkingDirectory '%ROOT%' -RedirectStandardOutput '%RECORDER_OUT%' -RedirectStandardError '%RECORDER_ERR%' -WindowStyle Hidden -PassThru; $p.Id"') do set "RECORDER_PID=%%p"
if "%RECORDER_PID%"=="" (
    echo ERROR: Could not start master_recorder.
    call :stop_process %COLLECTOR_PID%
    exit /b 1
)
echo [OK] Master recorder started with PID %RECORDER_PID%

echo [4/7] Capture running. Will stop at 15:45 IST...
:WAIT_FOR_1545
call :get_ist_hhmm
call :get_ist_clock
if !IST_HHMM! GEQ 1545 goto STOP_CAPTURE
echo   IST !IST_CLOCK! - capture active.
timeout /t 60 /nobreak >nul
goto WAIT_FOR_1545

:STOP_CAPTURE
echo [5/7] Stopping capture at 15:45 IST...
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Method Post 'http://localhost:8080/recorder/stop?provider=fyers' | Out-Null } catch {}"
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Method Post 'http://localhost:8080/recorder/stop?provider=upstox' | Out-Null } catch {}"
call :stop_process %RECORDER_PID%

:POST_MARKET
echo [6/7] Stopping Data Collector service...
call :stop_process %COLLECTOR_PID%

echo [7/7] Running post-market pipeline for %TRADE_DATE%...
set "PIPELINE_FAILED=0"

"%PYTHON_EXE%" "%LIB_DIR%\verify_eod_live_capture.py" --date %TRADE_DATE%
if errorlevel 1 set "PIPELINE_FAILED=1"

"%PYTHON_EXE%" "%LIB_DIR%\audit_timezone_integrity.py" --provider all --start-date %TRADE_DATE% --end-date %TRADE_DATE%
if errorlevel 1 set "PIPELINE_FAILED=1"

call "%ROOT%\scripts\run_eod_tick_aggregation.bat" --date %TRADE_DATE%
if errorlevel 1 set "PIPELINE_FAILED=1"

"%PYTHON_EXE%" "%LIB_DIR%\db_backup.py"
if errorlevel 1 set "PIPELINE_FAILED=1"

echo.
echo ================== WORKFLOW COMPLETE ==================
echo Collector logs: %COLLECTOR_OUT% and %COLLECTOR_ERR%
echo Recorder logs:  %RECORDER_OUT% and %RECORDER_ERR%
if "%PIPELINE_FAILED%"=="1" (
    echo Status: COMPLETED WITH FAILURES (check logs above)
    exit /b 1
)
echo Status: SUCCESS
exit /b 0

:get_ist_hhmm
for /f %%i in ('powershell -NoProfile -Command "$ist=[System.TimeZoneInfo]::FindSystemTimeZoneById('India Standard Time'); $now=[System.TimeZoneInfo]::ConvertTimeFromUtc((Get-Date).ToUniversalTime(),$ist); $now.ToString('HHmm')"') do set "IST_HHMM=%%i"
exit /b

:get_ist_clock
for /f %%i in ('powershell -NoProfile -Command "$ist=[System.TimeZoneInfo]::FindSystemTimeZoneById('India Standard Time'); $now=[System.TimeZoneInfo]::ConvertTimeFromUtc((Get-Date).ToUniversalTime(),$ist); $now.ToString('HH:mm:ss')"') do set "IST_CLOCK=%%i"
exit /b

:get_ist_date
for /f %%i in ('powershell -NoProfile -Command "$ist=[System.TimeZoneInfo]::FindSystemTimeZoneById('India Standard Time'); $now=[System.TimeZoneInfo]::ConvertTimeFromUtc((Get-Date).ToUniversalTime(),$ist); $now.ToString('yyyy-MM-dd')"') do set "IST_DATE=%%i"
exit /b

:get_timestamp
for /f %%i in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMdd_HHmmss')"') do set "TS=%%i"
exit /b

:stop_process
set "TARGET_PID=%~1"
if "%TARGET_PID%"=="" exit /b
powershell -NoProfile -Command "if (Get-Process -Id %TARGET_PID% -ErrorAction SilentlyContinue) { Stop-Process -Id %TARGET_PID% -Force }"
exit /b
