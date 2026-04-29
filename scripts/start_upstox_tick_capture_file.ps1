#Requires -Version 5.1
param(
    [string]$Expiry = "",
    [string]$Expiries = "",
    [int]$StrikeCount = 21,
    [int]$MaxSymbols = 0,
    [ValidateSet("lite", "full")]
    [string]$Mode = "full"
)

$ErrorActionPreference = 'Stop'

$ROOT = (Get-Item "$PSScriptRoot\..").FullName
$PYTHON_EXE = "$ROOT\services\data_collector\.venv\Scripts\python.exe"
$RECORDER = "$ROOT\scripts\lib\quick_live_recorder.py"

if (-not (Test-Path $PYTHON_EXE)) {
    Write-Error "Missing virtual environment for data_collector. Expected: $PYTHON_EXE"
    exit 1
}

if (-not (Test-Path $RECORDER)) {
    Write-Error "Recorder script not found: $RECORDER"
    exit 1
}

Write-Host "==============================================="
Write-Host "Upstox Tick Capture (File + DB)"
Write-Host "Provider:   upstox"
Write-Host "Mode:       $Mode"
Write-Host "Strikes:    ATM +/- $StrikeCount (CE/PE)"
Write-Host "Tick files: $ROOT\logs\ticks"
Write-Host "==============================================="

$args = @(
    $RECORDER,
    "--provider", "upstox",
    "--strike-count", "$StrikeCount",
    "--mode", $Mode,
    "--non-interactive"
)

if (-not [string]::IsNullOrWhiteSpace($Expiries)) {
    $args += @("--expiries", $Expiries)
}
elseif (-not [string]::IsNullOrWhiteSpace($Expiry)) {
    $args += @("--expiry", $Expiry)
}

if ($MaxSymbols -gt 0) {
    $args += @("--max-symbols", "$MaxSymbols")
}

& $PYTHON_EXE @args
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Error "Tick capture exited with code $exitCode"
    exit $exitCode
}

exit 0
