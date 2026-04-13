#Requires -Version 5.1
param()

$ErrorActionPreference = 'Stop'

$ROOT          = (Get-Item "$PSScriptRoot\..").FullName
$PYTHON_EXE    = "$ROOT\services\data_collector\.venv\Scripts\python.exe"
$COLLECTOR_DIR = "$ROOT\services\data_collector"
$LIB_DIR       = "$ROOT\scripts\lib"
$LOG_DIR       = "$ROOT\logs\daily_capture"

$env:PYTHONPATH          = $ROOT
$env:TRADING_CONFIG_DIR  = "$ROOT\config"
$env:TRADING_AUTH_DIR    = "$ROOT\config\auth"

if (-not (Test-Path $PYTHON_EXE)) {
    Write-Error "ERROR: Missing virtual environment at services\data_collector\.venv"
    exit 1
}
if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

$IST_TZ = [System.TimeZoneInfo]::FindSystemTimeZoneById("India Standard Time")
function Get-ISTNow { [System.TimeZoneInfo]::ConvertTimeFromUtc((Get-Date).ToUniversalTime(), $script:IST_TZ) }

$TRADE_DATE    = (Get-ISTNow).ToString("yyyy-MM-dd")
$RUN_STAMP     = (Get-Date).ToString("yyyyMMdd_HHmmss")
$COLLECTOR_OUT = "$LOG_DIR\collector_${RUN_STAMP}.out.log"
$COLLECTOR_ERR = "$LOG_DIR\collector_${RUN_STAMP}.err.log"
$RECORDER_OUT  = "$LOG_DIR\master_recorder_${RUN_STAMP}.out.log"
$RECORDER_ERR  = "$LOG_DIR\master_recorder_${RUN_STAMP}.err.log"

Write-Host "================================================================"
Write-Host "DAILY LIVE CAPTURE + EOD PIPELINE"
Write-Host "IST Trade Date : $TRADE_DATE"
Write-Host "Run Stamp      : $RUN_STAMP"
Write-Host "Collector log  : $COLLECTOR_OUT"
Write-Host "Recorder log   : $RECORDER_OUT"
Write-Host "================================================================"

# Step 1 - Start Data Collector in background
Write-Host ""
Write-Host "[1/7] Starting Data Collector service..."
$CollectorProc = Start-Process `
    -FilePath         $PYTHON_EXE `
    -ArgumentList     "main.py" `
    -WorkingDirectory $COLLECTOR_DIR `
    -RedirectStandardOutput $COLLECTOR_OUT `
    -RedirectStandardError  $COLLECTOR_ERR `
    -NoNewWindow `
    -PassThru

if (-not $CollectorProc) {
    Write-Error "ERROR: Failed to start Data Collector."
    exit 1
}
Write-Host "[OK] Data Collector started with PID $($CollectorProc.Id). Waiting 10s for FastAPI startup..."
Start-Sleep -Seconds 10

try {
    $resp = Invoke-WebRequest -UseBasicParsing "http://localhost:8080/health" -TimeoutSec 5
    Write-Host "[OK] Data Collector is responding (HTTP $($resp.StatusCode))."
} catch {
    Write-Host "[WARN] Port 8080 not responding yet. Check $COLLECTOR_OUT if issues persist."
}

# Step 2 - Manual authentication gate
Write-Host ""
Write-Host "[2/7] Authentication gate."
Write-Host "Checking and refreshing broker auth (Fyers / Upstox) as needed..."
Write-Host ""
Write-Host "Current auth status:"
& $PYTHON_EXE "$LIB_DIR\verify_auth.py"

$providers = @("fyers", "upstox")
foreach ($provider in $providers) {
    $authOk = $false
    try {
        $statusResp = Invoke-WebRequest -UseBasicParsing "http://localhost:8080/auth/status?provider=$provider" -TimeoutSec 10
        $statusJson = $statusResp.Content | ConvertFrom-Json
        $authOk = [bool]$statusJson.authenticated
    } catch {
        Write-Host "[WARN] Could not fetch auth status for $provider via API."
    }

    if ($authOk) {
        Write-Host "[OK] $provider session already valid."
        continue
    }

    Write-Host "[AUTH] $provider requires login."
    try {
        $urlResp = Invoke-WebRequest -UseBasicParsing "http://localhost:8080/auth/url?provider=$provider" -TimeoutSec 10
        $urlJson = $urlResp.Content | ConvertFrom-Json
        if ($urlJson.url) {
            Write-Host "  Auth URL: $($urlJson.url)"
        }
    } catch {
        Write-Host "[WARN] Could not fetch auth URL for $provider via API."
    }

    $runNow = Read-Host "Run built-in auth now for ${provider}? (Y/n)"
    if (($runNow -eq "") -or ($runNow -match "^[Yy]$")) {
        & $PYTHON_EXE "$LIB_DIR\authenticate.py" --provider $provider
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[WARN] authenticate.py failed for $provider (exit $LASTEXITCODE)."
        }
    }
}

Write-Host ""
Write-Host "Post-auth status:"
& $PYTHON_EXE "$LIB_DIR\verify_auth.py"

$invalidProviders = @()
foreach ($provider in $providers) {
    try {
        $statusResp = Invoke-WebRequest -UseBasicParsing "http://localhost:8080/auth/status?provider=$provider" -TimeoutSec 10
        $statusJson = $statusResp.Content | ConvertFrom-Json
        if (-not [bool]$statusJson.authenticated) {
            $invalidProviders += $provider
        }
    } catch {
        $invalidProviders += $provider
    }
}

if ($invalidProviders.Count -gt 0) {
    Write-Host "[WARN] Still unauthenticated: $($invalidProviders -join ', ')."
    $continueAnyway = Read-Host "Continue capture anyway? (y/N)"
    if ($continueAnyway -notmatch "^[Yy]$") {
        if (-not $CollectorProc.HasExited) {
            Stop-Process -Id $CollectorProc.Id -Force -ErrorAction SilentlyContinue
        }
        Write-Host "[INFO] Workflow aborted by user due to auth status."
        exit 1
    }
}

# Step 3 - Wait until 09:00 IST if launched early, then start capture
$RecorderProc = $null
$istHHMM = [int]((Get-ISTNow).ToString("HHmm"))

if ($istHHMM -ge 1545) {
    Write-Host "[INFO] IST time is already past 15:45 - skipping capture window."
} else {
    if ($istHHMM -lt 900) {
        Write-Host "[3/7] Waiting until 09:00 IST to start capture (checks every 30s)..."
        while ([int]((Get-ISTNow).ToString("HHmm")) -lt 900) {
            Write-Host "  IST $((Get-ISTNow).ToString('HH:mm:ss')) - waiting for 09:00..."
            Start-Sleep -Seconds 30
        }
    }

    Write-Host "[3/7] Starting capture workers at IST $((Get-ISTNow).ToString('HH:mm:ss'))..."
    $RecorderProc = Start-Process `
        -FilePath         $PYTHON_EXE `
        -ArgumentList     "$LIB_DIR\master_recorder.py", "--python", $PYTHON_EXE `
        -WorkingDirectory $ROOT `
        -RedirectStandardOutput $RECORDER_OUT `
        -RedirectStandardError  $RECORDER_ERR `
        -NoNewWindow `
        -PassThru

    if (-not $RecorderProc) {
        Write-Error "ERROR: Failed to start master_recorder."
        Stop-Process -Id $CollectorProc.Id -Force -ErrorAction SilentlyContinue
        exit 1
    }
    Write-Host "[OK] Master recorder started with PID $($RecorderProc.Id)"

    # Step 4 - Hold until 15:45 IST
    Write-Host "[4/7] Capture running. Auto-stop at 15:45 IST. Press Ctrl+C to abort early."
    try {
        while ([int]((Get-ISTNow).ToString("HHmm")) -lt 1545) {
            Write-Host "  IST $((Get-ISTNow).ToString('HH:mm:ss')) - capture active."
            Start-Sleep -Seconds 60
        }
    } catch {
        Write-Host "[INFO] Capture loop exited: $_"
    }

    # Step 5 - Stop capture
    Write-Host ""
    Write-Host "[5/7] Stopping capture at IST $((Get-ISTNow).ToString('HH:mm:ss'))..."
    try { Invoke-WebRequest -UseBasicParsing -Method Post "http://localhost:8080/recorder/stop?provider=fyers"  | Out-Null } catch {}
    try { Invoke-WebRequest -UseBasicParsing -Method Post "http://localhost:8080/recorder/stop?provider=upstox" | Out-Null } catch {}
    Start-Sleep -Seconds 3
    if ($RecorderProc -and -not $RecorderProc.HasExited) {
        Stop-Process -Id $RecorderProc.Id -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Recorder process terminated."
    }
}

# Step 6 - Stop Data Collector
Write-Host ""
Write-Host "[6/7] Stopping Data Collector..."
if (-not $CollectorProc.HasExited) {
    Stop-Process -Id $CollectorProc.Id -Force -ErrorAction SilentlyContinue
    Write-Host "[OK] Data Collector stopped."
} else {
    Write-Host "[INFO] Data Collector had already exited."
}

# Step 7 - Post-market pipeline
Write-Host ""
Write-Host "[7/7] Post-market pipeline for $TRADE_DATE..."
$pipelineFailed = $false

Write-Host "  [7a] EOD live capture verification..."
& $PYTHON_EXE "$LIB_DIR\verify_eod_live_capture.py" --date $TRADE_DATE
if ($LASTEXITCODE -ne 0) { $pipelineFailed = $true; Write-Host "  [WARN] verify_eod_live_capture reported failures." }

Write-Host "  [7b] Timezone integrity audit..."
& $PYTHON_EXE "$LIB_DIR\audit_timezone_integrity.py" --provider all --start-date $TRADE_DATE --end-date $TRADE_DATE
if ($LASTEXITCODE -ne 0) { $pipelineFailed = $true; Write-Host "  [WARN] audit_timezone_integrity reported failures." }

Write-Host "  [7c] Tick aggregation (Fyers + Upstox)..."
& "$ROOT\scripts\run_eod_tick_aggregation.bat" --date $TRADE_DATE
if ($LASTEXITCODE -ne 0) { $pipelineFailed = $true; Write-Host "  [WARN] Tick aggregation reported failures." }

Write-Host "  [7d] DB backup..."
& $PYTHON_EXE "$LIB_DIR\db_backup.py"
if ($LASTEXITCODE -ne 0) { $pipelineFailed = $true; Write-Host "  [WARN] DB backup reported failures." }

Write-Host ""
Write-Host "================== WORKFLOW COMPLETE =================="
Write-Host "Collector log : $COLLECTOR_OUT"
Write-Host "Recorder log  : $RECORDER_OUT"
if ($pipelineFailed) {
    Write-Host "Status: COMPLETED WITH FAILURES (check logs above)"
    exit 1
}
Write-Host "Status: SUCCESS"
exit 0
