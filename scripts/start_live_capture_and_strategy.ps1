#Requires -Version 5.1
param(
    [string]$Strategy = "ema_cross",
    [string]$EnvFile = "",
    [int]$StrikeCount = 21,
    [switch]$SkipAuthCheck
)

$ErrorActionPreference = 'Stop'

$ROOT = (Get-Item "$PSScriptRoot\..").FullName
$PYTHON_EXE_COLLECTOR = "$ROOT\services\data_collector\.venv\Scripts\python.exe"
$PYTHON_EXE_RUNTIME = "$ROOT\.venv\Scripts\python.exe"
$COLLECTOR_MAIN = "$ROOT\services\data_collector\main.py"
$MASTER_RECORDER = "$ROOT\scripts\lib\master_recorder.py"
$RUNTIME_SERVER = "$ROOT\services\strategy_runtime\server.py"

Write-Host "==============================================="
Write-Host "Astra: Unified Live Capture + Strategy Runtime"
Write-Host "Mode:  Live Data -> Paper Trading"
Write-Host "==============================================="

# 1. Start Data Collector if not running
function Test-PortListening {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return (($connections | Measure-Object).Count -gt 0)
}

if (-not (Test-PortListening -Port 8080)) {
    Write-Host "[1/3] Starting Data Collector service..."
    Start-Process -FilePath $PYTHON_EXE_COLLECTOR -ArgumentList $COLLECTOR_MAIN -WorkingDirectory "$ROOT\services\data_collector" -NoNewWindow
    Start-Sleep -Seconds 8
} else {
    Write-Host "[1/3] Data Collector already running on port 8080."
}

# 2. Start Master Recorder for Capture
Write-Host "[2/3] Starting Master Recorder (Tick Capture)..."
$recorderArgs = @($MASTER_RECORDER, "--strike-count", "$StrikeCount", "--python", $PYTHON_EXE_COLLECTOR)
Start-Process -FilePath $PYTHON_EXE_COLLECTOR -ArgumentList $recorderArgs -WorkingDirectory $ROOT

# 3. Start Strategy Runtime
Write-Host "[3/3] Starting Strategy Runtime ($Strategy)..."
$runtimeEnv = if ($EnvFile) { $EnvFile } else { "config\strategy_runtime.$Strategy.paper_live.env" }
$runtimeArgs = @("$PSScriptRoot\start_strategy_runtime_live_paper.ps1", "-Strategy", $Strategy, "-EnvFile", $runtimeEnv)
if ($SkipAuthCheck) { $runtimeArgs += "-SkipAuthCheck" }

# We launch the runtime in the current window as it's the primary interactive component
& powershell.exe -File @runtimeArgs

Write-Host "==============================================="
Write-Host "Shutdown: Closing background processes..."
# Note: Data Collector and Recorder might stay running depending on OS process tree.
# Usually, master_recorder.py manages its own children.
Write-Host "Done."
