#Requires -Version 5.1
param(
    [string]$EnvFile = "",
    [string]$Strategy = "ema_cross",
    [switch]$SkipAuthCheck,
    [switch]$NonInteractiveAuth
)

$ErrorActionPreference = 'Stop'

$ROOT = (Get-Item "$PSScriptRoot\..").FullName
$PYTHON_EXE = "$ROOT\.venv\Scripts\python.exe"
$RUNTIME_SERVER = "$ROOT\services\strategy_runtime\server.py"
$AUTH_HELPER = "$ROOT\scripts\authenticate_broker.py"
$LOG_DIR = "$ROOT\logs\strategy_runtime"
$AUTH_DIR = "$ROOT\config\auth"

function Read-EnvFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Env file not found: $Path"
    }

    $loaded = @{}
    $lines = Get-Content -Path $Path -Encoding UTF8
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if (-not $trimmed) { continue }
        if ($trimmed.StartsWith("#")) { continue }

        $parts = $trimmed -split '=', 2
        if ($parts.Count -ne 2) { continue }

        $key = $parts[0].Trim()
        $value = $parts[1].Trim()

        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        [Environment]::SetEnvironmentVariable($key, $value, 'Process')
        $loaded[$key] = $value
    }

    return $loaded
}

if (-not (Test-Path $PYTHON_EXE)) {
    Write-Error "Missing Python virtual environment at .venv. Expected: $PYTHON_EXE"
    exit 1
}

if (-not (Test-Path $RUNTIME_SERVER)) {
    Write-Error "Missing runtime server entrypoint: $RUNTIME_SERVER"
    exit 1
}

if (-not (Test-Path $AUTH_HELPER)) {
    Write-Error "Missing authentication helper script: $AUTH_HELPER"
    exit 1
}

$defaultStrategyEnv = Join-Path $ROOT "config\strategy_runtime.$Strategy.paper_live.env"
$defaultGenericEnv = Join-Path $ROOT "config\strategy_runtime.paper_live.env"

if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    if (Test-Path $defaultStrategyEnv) {
        $envPath = $defaultStrategyEnv
    }
    elseif (Test-Path $defaultGenericEnv) {
        $envPath = $defaultGenericEnv
    }
    else {
        Write-Error "No env file found. Checked $defaultStrategyEnv and $defaultGenericEnv"
        exit 1
    }
}
else {
    $envPath = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $ROOT $EnvFile }
}

$loadedEnv = Read-EnvFile -Path $envPath

if (-not (Test-Path $LOG_DIR)) {
    New-Item -Path $LOG_DIR -ItemType Directory -Force | Out-Null
}

$tradingCorePath = "$ROOT\packages\trading_core"
$env:PYTHONPATH = "$ROOT;$tradingCorePath"
$env:TRADING_CONFIG_DIR = "$ROOT\config"
$env:TRADING_AUTH_DIR = $AUTH_DIR

# Enforce live-paper defaults unless explicitly overridden in env file.
if (-not $loadedEnv.ContainsKey("STRATEGY_RUNTIME_FEED_SOURCE")) {
    [Environment]::SetEnvironmentVariable("STRATEGY_RUNTIME_FEED_SOURCE", "broker", 'Process')
}
if (-not $loadedEnv.ContainsKey("STRATEGY_RUNTIME_TRADING_PROVIDER")) {
    [Environment]::SetEnvironmentVariable("STRATEGY_RUNTIME_TRADING_PROVIDER", "paper", 'Process')
}
if (-not $loadedEnv.ContainsKey("STRATEGY_RUNTIME_TIMEFRAME")) {
    [Environment]::SetEnvironmentVariable("STRATEGY_RUNTIME_TIMEFRAME", "5m", 'Process')
}

Write-Host "==============================================="
Write-Host "Strategy Runtime Live Paper Launcher"
Write-Host "Root:      $ROOT"
Write-Host "Env file:  $envPath"
Write-Host "Python:    $PYTHON_EXE"
Write-Host "Auth dir:  $AUTH_DIR"
Write-Host "==============================================="

Write-Host "Loaded environment keys:"
($loadedEnv.Keys | Sort-Object) | ForEach-Object { Write-Host "  - $_" }

if (-not (Test-Path (Join-Path $AUTH_DIR ".upstox_access_token.txt")) -and -not (Test-Path (Join-Path $AUTH_DIR ".access_token.txt"))) {
    Write-Warning "No token files found in config/auth. Runtime may start but broker polling can fail until auth is refreshed."
}

if (-not $SkipAuthCheck) {
    $provider = [Environment]::GetEnvironmentVariable("STRATEGY_RUNTIME_PROVIDER", "Process")
    if ([string]::IsNullOrWhiteSpace($provider)) {
        $provider = "upstox"
    }

    Write-Host ""
    Write-Host "Checking broker authentication for provider: $provider"

    $authArgs = @($AUTH_HELPER, "--provider", $provider)
    if ($NonInteractiveAuth) {
        $authArgs += "--non-interactive"
    }

    & $PYTHON_EXE @authArgs
    $authExit = $LASTEXITCODE
    if ($authExit -ne 0) {
        Write-Error "Authentication check failed with exit code $authExit. Use -SkipAuthCheck to bypass (not recommended)."
        exit $authExit
    }
}

Write-Host ""
Write-Host "Starting Strategy Runtime API in live-paper mode..."
Write-Host "Press Ctrl+C to stop."

& $PYTHON_EXE $RUNTIME_SERVER
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Error "Runtime server exited with code $exitCode"
    exit $exitCode
}

exit 0
