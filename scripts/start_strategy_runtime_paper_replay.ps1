#Requires -Version 5.1
<#
.SYNOPSIS
    Start strategy runtime in paper replay mode.

.DESCRIPTION
    Launches strategy runtime and optionally starts replay engine.

    Parameter convention:
    - Canonical: StrategyConfig, Strategy, StartReplayEngine
    - Legacy aliases: EnvFile -> StrategyConfig, StrategyName -> Strategy,
      SkipReplayEngine retained for compatibility
#>
param(
    [Alias("EnvFile")]
    [string]$StrategyConfig = "",
    [Alias("StrategyName")]
    [string]$Strategy = "ema_cross",
    [switch]$StartReplayEngine,
    [switch]$SkipReplayEngine
)

$ErrorActionPreference = 'Stop'

$ROOT = (Get-Item "$PSScriptRoot\..").FullName
$PYTHON_EXE = "$ROOT\.venv\Scripts\python.exe"
$RUNTIME_SERVER = "$ROOT\services\strategy_runtime\server.py"
$REPLAY_MAIN = "$ROOT\services\replay_engine\main.py"
$LOG_DIR = "$ROOT\logs\strategy_runtime"

if ($PSBoundParameters.ContainsKey("StartReplayEngine") -and $PSBoundParameters.ContainsKey("SkipReplayEngine")) {
    Write-Error "Use either -StartReplayEngine or -SkipReplayEngine, not both."
    exit 1
}

$shouldStartReplayEngine = $true
if ($PSBoundParameters.ContainsKey("SkipReplayEngine")) {
    $shouldStartReplayEngine = -not [bool]$SkipReplayEngine
} elseif ($PSBoundParameters.ContainsKey("StartReplayEngine")) {
    $shouldStartReplayEngine = [bool]$StartReplayEngine
}

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

function Read-JsonConfig {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Config file not found: $Path"
    }

    $json = Get-Content -Path $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    $loaded = @{}

    if ($null -ne $json.runtime) {
        foreach ($prop in $json.runtime.PSObject.Properties) {
            $loaded["runtime.$($prop.Name)"] = [string]$prop.Value
        }
    }

    if ($null -ne $json.strategy_params) {
        foreach ($prop in $json.strategy_params.PSObject.Properties) {
            $value = if ($null -eq $prop.Value) { "" } else { [string]$prop.Value }
            [Environment]::SetEnvironmentVariable($prop.Name, $value, 'Process')
            $loaded[$prop.Name] = $value
        }
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

$defaultStrategyEnv = Join-Path $ROOT "config\strategy_runtime.$Strategy.paper_replay.json"
$defaultNiftyReplayEnv = Join-Path $ROOT "config\strategy_runtime.nifty_trend_options.replay_ticks.json.example"
$defaultGenericEnv = Join-Path $ROOT "config\strategy_runtime.paper_replay.json"

if ([string]::IsNullOrWhiteSpace($StrategyConfig)) {
    if (Test-Path $defaultStrategyEnv) {
        $envPath = $defaultStrategyEnv
    }
    elseif ($Strategy -eq "nifty_trend_options" -and (Test-Path $defaultNiftyReplayEnv)) {
        $envPath = $defaultNiftyReplayEnv
    }
    elseif (Test-Path $defaultGenericEnv) {
        $envPath = $defaultGenericEnv
    }
    else {
        Write-Error "No config file found. Checked $defaultStrategyEnv, $defaultNiftyReplayEnv and $defaultGenericEnv"
        exit 1
    }
}
else {
    $envPath = if ([System.IO.Path]::IsPathRooted($StrategyConfig)) { $StrategyConfig } else { Join-Path $ROOT $StrategyConfig }
}

$loadedEnv = Read-JsonConfig -Path $envPath
[Environment]::SetEnvironmentVariable("STRATEGY_RUNTIME_CONFIG", $envPath, 'Process')

if (-not (Test-Path $LOG_DIR)) {
    New-Item -Path $LOG_DIR -ItemType Directory -Force | Out-Null
}

$tradingCorePath = "$ROOT\packages\trading_core"
$env:PYTHONPATH = "$ROOT;$tradingCorePath"
$env:TRADING_CONFIG_DIR = "$ROOT\config"
$env:TRADING_AUTH_DIR = "$ROOT\config\auth"

$stamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
$replayOut = Join-Path $LOG_DIR "replay_${stamp}.out.log"
$replayErr = Join-Path $LOG_DIR "replay_${stamp}.err.log"

$replayProc = $null

try {
    Write-Host "==============================================="
    Write-Host "Strategy Runtime Paper/Replay Launcher"
    Write-Host "Root:      $ROOT"
    Write-Host "Config:    $envPath"
    Write-Host "Python:    $PYTHON_EXE"
    Write-Host "==============================================="

    Write-Host "Loaded environment keys:"
    ($loadedEnv.Keys | Sort-Object) | ForEach-Object { Write-Host "  - $_" }

    if ($shouldStartReplayEngine) {
        if (-not (Test-Path $REPLAY_MAIN)) {
            throw "Replay engine entrypoint not found: $REPLAY_MAIN"
        }

        Write-Host ""
        Write-Host "Starting Replay Engine in background..."
        $replayProc = Start-Process `
            -FilePath $PYTHON_EXE `
            -ArgumentList $REPLAY_MAIN `
            -WorkingDirectory $ROOT `
            -RedirectStandardOutput $replayOut `
            -RedirectStandardError $replayErr `
            -PassThru

        Write-Host "Replay PID: $($replayProc.Id)"
        Write-Host "Replay logs: $replayOut"
        Start-Sleep -Seconds 2
    }

    Write-Host ""
    Write-Host "Starting Strategy Runtime API..."
    Write-Host "Press Ctrl+C to stop."

    & $PYTHON_EXE $RUNTIME_SERVER --config $envPath
    $exitCode = $LASTEXITCODE
}
finally {
    if ($shouldStartReplayEngine -and $replayProc -and -not $replayProc.HasExited) {
        Write-Host ""
        Write-Host "Stopping Replay Engine PID $($replayProc.Id)..."
        Stop-Process -Id $replayProc.Id -Force -ErrorAction SilentlyContinue
    }
}

if ($exitCode -ne 0) {
    Write-Error "Runtime server exited with code $exitCode"
    exit $exitCode
}

exit 0
