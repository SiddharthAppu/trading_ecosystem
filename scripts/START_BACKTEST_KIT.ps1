#Requires -Version 5.1
<#
.SYNOPSIS
    Astra Backtest Kit - Run strategy backtest or parameter optimisation.

.DESCRIPTION
    Runs strategy_backtest.py or strategy_optimize.py against historical data
    in TimescaleDB through the strategy_runtime offline adapter path. Prompts
    for a date range if not supplied via parameters.
    Requires only Python + DB credentials in config/.env — no running services needed.

.PARAMETER From
    Start date (YYYY-MM-DD). If omitted, you will be prompted.

.PARAMETER To
    End date (YYYY-MM-DD). Defaults to today if omitted.

.PARAMETER Mode
    backtest  - Run a single backtest (default)
    optimize  - Grid-search over NIFTY_* parameters

.PARAMETER Top
    (optimize mode) Number of top results to display. Default: 10

.PARAMETER Symbol
    Underlying symbol. Default: reads from config/.env or uses adapter default.

.PARAMETER Smoke
    Runs a quick adapter backtest smoke check and auto-generates a run name when
    not provided.

.EXAMPLE
    .\START_BACKTEST_KIT.ps1
    .\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28
    .\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28 -Mode optimize -Top 15
    .\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28 -Symbol "NSE_INDEX|Nifty 50"
    .\START_BACKTEST_KIT.ps1 -Smoke -From 2026-04-28 -To 2026-04-28
#>
param(
    [string]$From   = "",
    [string]$To     = "",
    [ValidateSet("backtest", "optimize")]
    [string]$Mode   = "backtest",
    [int]$Top       = 10,
    [string]$StrategyName = "",
    [string]$Timeframe = "",
    [string]$LogFile = "",
    [string]$RunName = "",
    [string]$RunNamePrefix = "opt",
    [ValidateSet("interactive", "non-interactive")]
    [string]$ConfirmationMode = "interactive",
    [switch]$Smoke,
    [string]$Symbol = "",
    [string]$EnvFile = "",
    [string]$StrategyConfig = ""
)

$ErrorActionPreference = 'Stop'

# ── Resolve kit root ───────────────────────────────────────────────────────────
$scriptDir = $PSScriptRoot
$scriptDirLeaf = Split-Path -Path $scriptDir -Leaf
if ($scriptDirLeaf -ieq "scripts") {
    $KIT_ROOT = Split-Path -Path $scriptDir -Parent
} else {
    $KIT_ROOT = $scriptDir
}
$PYTHON_EXE  = "$KIT_ROOT\.venv\Scripts\python.exe"
$BACKTEST_PY = "$KIT_ROOT\scripts\strategy_backtest.py"
$OPTIMIZE_PY = "$KIT_ROOT\scripts\strategy_optimize.py"
$STRATEGY_RUNTIME_DIR = "$KIT_ROOT\services\strategy_runtime"
$OFFLINE_ADAPTER_RUNNER = "$STRATEGY_RUNTIME_DIR\offline_adapter\runner.py"
$RUNTIME_REQUIREMENTS = "$STRATEGY_RUNTIME_DIR\astra-kit-requirements.txt"
$GLOBAL_ENV  = if ($EnvFile) { if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $KIT_ROOT $EnvFile } } else { "$KIT_ROOT\config\.env" }
$STRATEGY_ENV = if ($StrategyConfig) { if ([System.IO.Path]::IsPathRooted($StrategyConfig)) { $StrategyConfig } else { Join-Path $KIT_ROOT $StrategyConfig } } else { "$KIT_ROOT\config\strategy_runtime.paper_replay.env" }

# ── Banner ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "      Astra Backtest Kit - Strategy Backtest Analyser      " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# ── Smoke mode normalization ──────────────────────────────────────────────────
if ($Smoke) {
    if ($Mode -ne "backtest") {
        Write-Host "[INFO] Smoke mode forcing Mode=backtest" -ForegroundColor DarkGray
        $Mode = "backtest"
    }
    if ([string]::IsNullOrWhiteSpace($RunName)) {
        $RunName = "smoke_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    }
}

# ── Pre-flight checks ──────────────────────────────────────────────────────────
if (-not (Test-Path $PYTHON_EXE)) {
    Write-Host "[ERROR] Python virtual environment not found at .venv\" -ForegroundColor Red
    Write-Host "        Run: python -m venv .venv" -ForegroundColor Yellow
    Write-Host "        Then: .venv\Scripts\pip install -e packages\trading_core" -ForegroundColor Yellow
    Write-Host "        Then: .venv\Scripts\pip install -r services\strategy_runtime\astra-kit-requirements.txt psycopg2-binary" -ForegroundColor Yellow
    exit 1
}

$targetScript = if ($Mode -eq "optimize") { $OPTIMIZE_PY } else { $BACKTEST_PY }
if (-not (Test-Path $targetScript)) {
    Write-Host "[ERROR] Script not found: $targetScript" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $OFFLINE_ADAPTER_RUNNER)) {
    Write-Host "[ERROR] strategy_runtime offline adapter not found: $OFFLINE_ADAPTER_RUNNER" -ForegroundColor Red
    Write-Host "        This backtest kit appears to be missing services\strategy_runtime." -ForegroundColor Yellow
    Write-Host "        Rebuild the kit from the workspace using:" -ForegroundColor Yellow
    Write-Host "        powershell -ExecutionPolicy Bypass -File .\scripts\build_replay_backtest_kits.ps1 -Version v1" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $RUNTIME_REQUIREMENTS)) {
    Write-Host "[WARN] Runtime requirements manifest not found: $RUNTIME_REQUIREMENTS" -ForegroundColor Yellow
    Write-Host "       If dependencies are missing, install them with:" -ForegroundColor Yellow
    Write-Host "       .venv\Scripts\pip install -r services\strategy_runtime\astra-kit-requirements.txt psycopg2-binary" -ForegroundColor Yellow
}

# ── Load global env (DB credentials etc.) ─────────────────────────────────────
function Import-EnvFile([string]$Path) {
    if (-not (Test-Path $Path)) { return }
    foreach ($line in (Get-Content $Path -Encoding UTF8)) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith('#')) { continue }
        $parts = $t -split '=', 2
        if ($parts.Count -ne 2) { continue }
        $k = $parts[0].Trim()
        $v = $parts[1].Trim()
        if (($v.StartsWith('"') -and $v.EndsWith('"')) -or ($v.StartsWith("'") -and $v.EndsWith("'"))) {
            $v = $v.Substring(1, $v.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($k, $v, 'Process')
    }
}

function Normalize-DateInput {
    param(
        [string]$Value,
        [string]$FieldName
    )

    $trimmed = $Value.Trim()
    if ($trimmed -match '^\d{4}-\d{2}-\d{2}$') {
        return $trimmed
    }

    $parsed = [datetime]::MinValue
    if ([datetime]::TryParse($trimmed, [ref]$parsed)) {
        return $parsed.ToString("yyyy-MM-dd")
    }

    Write-Host "[ERROR] Invalid $FieldName date: $Value" -ForegroundColor Red
    Write-Host "        Use YYYY-MM-DD (example: 2026-04-30) or a parseable datetime (example: 2026-04-30T09:15:00+05:30)." -ForegroundColor Yellow
    exit 1
}

if (Test-Path $GLOBAL_ENV) {
    Import-EnvFile $GLOBAL_ENV
    Write-Host "[INFO] Loaded credentials from $GLOBAL_ENV" -ForegroundColor DarkGray
} else {
    Write-Host "[WARN] Env file not found: $GLOBAL_ENV" -ForegroundColor Yellow
    Write-Host "       DB connection may fail if credentials are missing." -ForegroundColor Yellow
}

if (Test-Path $STRATEGY_ENV) {
    Import-EnvFile $STRATEGY_ENV
    Write-Host "[INFO] Loaded strategy config from $STRATEGY_ENV" -ForegroundColor DarkGray
} else {
    Write-Host "[WARN] Strategy config not found: $STRATEGY_ENV" -ForegroundColor Yellow
    Write-Host "       Continuing with CLI values/defaults for strategy metadata." -ForegroundColor Yellow
}

$effectiveStrategyName = if ($PSBoundParameters.ContainsKey("StrategyName") -and -not [string]::IsNullOrWhiteSpace($StrategyName)) {
    $StrategyName
} elseif (-not [string]::IsNullOrWhiteSpace($env:STRATEGY_RUNTIME_STRATEGY)) {
    $env:STRATEGY_RUNTIME_STRATEGY
} else {
    "nifty_trend_options"
}

$effectiveTimeframe = if ($PSBoundParameters.ContainsKey("Timeframe") -and -not [string]::IsNullOrWhiteSpace($Timeframe)) {
    $Timeframe
} elseif (-not [string]::IsNullOrWhiteSpace($env:STRATEGY_RUNTIME_TIMEFRAME)) {
    $env:STRATEGY_RUNTIME_TIMEFRAME
} else {
    "5m"
}

$effectiveLogFile = if ($PSBoundParameters.ContainsKey("LogFile") -and -not [string]::IsNullOrWhiteSpace($LogFile)) {
    $LogFile
} elseif (-not [string]::IsNullOrWhiteSpace($env:STRATEGY_RUNTIME_LOG_FILE)) {
    $env:STRATEGY_RUNTIME_LOG_FILE
} else {
    "logs/strategy_runtime/runtime.log"
}

$effectiveIndexSymbol = if ($Symbol -ne "") {
    $Symbol
} else {
    "NSE:NIFTY50-INDEX"
}
$strategyNameSource = if ($PSBoundParameters.ContainsKey("StrategyName") -and -not [string]::IsNullOrWhiteSpace($StrategyName)) {
    "CLI"
} elseif (-not [string]::IsNullOrWhiteSpace($env:STRATEGY_RUNTIME_STRATEGY)) {
    "config"
} else {
    "default"
}

$timeframeSource = if ($PSBoundParameters.ContainsKey("Timeframe") -and -not [string]::IsNullOrWhiteSpace($Timeframe)) {
    "CLI"
} elseif (-not [string]::IsNullOrWhiteSpace($env:STRATEGY_RUNTIME_TIMEFRAME)) {
    "config"
} else {
    "default"
}

$logFileSource = if ($PSBoundParameters.ContainsKey("LogFile") -and -not [string]::IsNullOrWhiteSpace($LogFile)) {
    "CLI"
} elseif (-not [string]::IsNullOrWhiteSpace($env:STRATEGY_RUNTIME_LOG_FILE)) {
    "config"
} else {
    "default"
}

# ── Runtime dependency preflight ─────────────────────────────────────────────
& $PYTHON_EXE -c "import psycopg2" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Missing required package: psycopg2" -ForegroundColor Red
    Write-Host "        Install dependencies in this kit with:" -ForegroundColor Yellow
    Write-Host "        .\.venv\Scripts\pip install -r .\services\strategy_runtime\astra-kit-requirements.txt psycopg2-binary" -ForegroundColor Yellow
    Write-Host "        .\.venv\Scripts\pip install -e .\packages\trading_core" -ForegroundColor Yellow
    exit 1
}

# ── Set PYTHONPATH ─────────────────────────────────────────────────────────────
$env:PYTHONPATH = "$KIT_ROOT\packages\trading_core"

Write-Host ""
Write-Host "[PREFLIGHT] Locked configuration summary" -ForegroundColor Cyan
Write-Host "  Strategy   : $effectiveStrategyName ($strategyNameSource)" -ForegroundColor White
Write-Host "  Timeframe  : $effectiveTimeframe ($timeframeSource)" -ForegroundColor White
Write-Host "  Log file   : $effectiveLogFile ($logFileSource)" -ForegroundColor White
Write-Host "  Index sym  : $effectiveIndexSymbol" -ForegroundColor White
Write-Host "  Mode       : $Mode" -ForegroundColor White

Write-Host ""
Write-Host "[PREFLIGHT] Table snapshot" -ForegroundColor Cyan
Write-Host "  Table      : master_broker.ohlcv_1m" -ForegroundColor White
Write-Host "  Table      : master_broker.options_ohlc_1m_fromupstox" -ForegroundColor White

$tableSnapshotScript = @'
import json
import os
import sys

import psycopg2

database_url = os.getenv("DATABASE_URL", "")
if not database_url:
    print(json.dumps({"ok": False, "error": "DATABASE_URL not set"}))
    raise SystemExit(0)

try:
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT count(*), min(time), max(time)
        FROM master_broker.ohlcv_1m
        WHERE symbol = %s
        """,
        (sys.argv[1],),
    )
    index_count, index_min_time, index_max_time = cur.fetchone()

    cur.execute(
        """
        SELECT count(*), min(time), max(time)
        FROM master_broker.options_ohlc_1m_fromupstox
        """
    )
    options_count, options_min_time, options_max_time = cur.fetchone()

    cur.close()
    conn.close()

    print(
        json.dumps(
            {
                "ok": True,
                "index_count": int(index_count or 0),
                "index_min_time": index_min_time.isoformat() if index_min_time else None,
                "index_max_time": index_max_time.isoformat() if index_max_time else None,
                "options_count": int(options_count or 0),
                "options_min_time": options_min_time.isoformat() if options_min_time else None,
                "options_max_time": options_max_time.isoformat() if options_max_time else None,
            }
        )
    )
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)}))
'@

$snapshotRaw = $tableSnapshotScript | & $PYTHON_EXE - $effectiveIndexSymbol 2>$null
$snapshot = $null
if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace(($snapshotRaw | Out-String))) {
    try {
        $snapshot = ($snapshotRaw | Out-String).Trim() | ConvertFrom-Json
    } catch {
        $snapshot = $null
    }
}

if ($null -ne $snapshot -and $snapshot.ok) {
    Write-Host "  Index rows : $($snapshot.index_count)" -ForegroundColor White
    Write-Host "  Index span : $($snapshot.index_min_time) -> $($snapshot.index_max_time)" -ForegroundColor White
    Write-Host "  Options rows: $($snapshot.options_count)" -ForegroundColor White
    Write-Host "  Options span: $($snapshot.options_min_time) -> $($snapshot.options_max_time)" -ForegroundColor White
} elseif ($null -ne $snapshot -and -not $snapshot.ok) {
    Write-Host "  [WARN] Table snapshot failed: $($snapshot.error)" -ForegroundColor Yellow
} else {
    Write-Host "  [WARN] Table snapshot returned no parseable output." -ForegroundColor Yellow
}

# ── Prompt for dates if not provided ──────────────────────────────────────────
if ($From -eq "") {
    $From = Read-Host "Enter start date [YYYY-MM-DD]"
}

if ($To -eq "") {
    $defaultTo = (Get-Date).ToString("yyyy-MM-dd")
    $toInput = Read-Host "Enter end date [YYYY-MM-DD] (default: $defaultTo)"
    $To = if ($toInput.Trim() -eq "") { $defaultTo } else { $toInput.Trim() }
}

# ── Validate date format ───────────────────────────────────────────────────────
$From = Normalize-DateInput -Value $From -FieldName "start"
$To = Normalize-DateInput -Value $To -FieldName "end"

# ── Preflight data availability check ─────────────────────────────────────────
$indexTable = "master_broker.ohlcv_1m"
$optionsTable = "master_broker.options_ohlc_1m_fromupstox"

Write-Host "" 
Write-Host "[PREFLIGHT] Backtest data source summary" -ForegroundColor Cyan
Write-Host "  Index table   : $indexTable" -ForegroundColor White
Write-Host "  Options table : $optionsTable" -ForegroundColor White
Write-Host "  Index symbol  : $effectiveIndexSymbol" -ForegroundColor White
Write-Host "  Date range    : $From -> $To" -ForegroundColor White

$preflightScript = @'
import json
import os
import sys

import psycopg2

from_date = sys.argv[1]
to_date = sys.argv[2]
symbol = sys.argv[3]

database_url = os.getenv("DATABASE_URL", "")
if not database_url:
    print(json.dumps({"ok": False, "error": "DATABASE_URL not set"}))
    raise SystemExit(0)

try:
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT count(*)
        FROM master_broker.ohlcv_1m
        WHERE symbol = %s
          AND time >= %s::date
          AND time < (%s::date + INTERVAL '1 day')
          AND master_close IS NOT NULL
        """,
        (symbol, from_date, to_date),
    )
    index_count = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT count(*)
        FROM master_broker.options_ohlc_1m_fromupstox
        WHERE time >= %s::date
          AND time < (%s::date + INTERVAL '1 day')
          AND close IS NOT NULL
          AND close > 0
        """,
        (from_date, to_date),
    )
    options_count = int(cur.fetchone()[0])

    cur.close()
    conn.close()

    print(
        json.dumps(
            {
                "ok": True,
                "index_count": index_count,
                "options_count": options_count,
            }
        )
    )
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)}))
'@

$preflightRaw = $preflightScript | & $PYTHON_EXE - $From $To $effectiveIndexSymbol 2>$null
$preflight = $null
if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace(($preflightRaw | Out-String))) {
    try {
        $preflight = ($preflightRaw | Out-String).Trim() | ConvertFrom-Json
    } catch {
        $preflight = $null
    }
}

if ($null -ne $preflight -and $preflight.ok) {
    Write-Host "  Index rows    : $($preflight.index_count)" -ForegroundColor White
    Write-Host "  Option rows   : $($preflight.options_count)" -ForegroundColor White
    if ([int]$preflight.index_count -eq 0) {
        Write-Host "  [WARN] No index bars found in $indexTable for the selected date range/symbol." -ForegroundColor Yellow
    }
    if ([int]$preflight.options_count -eq 0) {
        Write-Host "  [WARN] No option rows found in $optionsTable for the selected date range." -ForegroundColor Yellow
    }
} elseif ($null -ne $preflight -and -not $preflight.ok) {
    Write-Host "  [WARN] Preflight row-count check failed: $($preflight.error)" -ForegroundColor Yellow
} else {
    Write-Host "  [WARN] Preflight row-count check returned no parseable output." -ForegroundColor Yellow
}

if ($ConfirmationMode -eq "interactive") {
    Write-Host ""
    $confirm = Read-Host "Proceed with $Mode run? [Y/N]"
    if ($confirm.Trim().ToUpper() -ne "Y") {
        Write-Host "[CANCELLED] $Mode not started by user choice." -ForegroundColor Yellow
        exit 0
    }
}

# ── Build argument list ────────────────────────────────────────────────────────
$args_list = @("--from", $From, "--to", $To)

$args_list += @(
    "--strategy-name", $effectiveStrategyName,
    "--timeframe", $effectiveTimeframe,
    "--log-file", $effectiveLogFile
)

if ($Symbol -ne "") {
    $args_list += @("--index-symbol", $Symbol)
}

if ($Mode -eq "optimize") {
    $args_list += @("--top", $Top)
    $args_list += @("--run-name-prefix", $RunNamePrefix)
} elseif ($RunName -ne "") {
    $args_list += @("--run-name", $RunName)
}

# ── Print run summary ──────────────────────────────────────────────────────────
Write-Host "Mode       : $Mode"              -ForegroundColor White
Write-Host "Date range : $From -> $To"       -ForegroundColor White
Write-Host "Strategy   : $effectiveStrategyName"      -ForegroundColor White
Write-Host "Timeframe  : $effectiveTimeframe"         -ForegroundColor White
Write-Host "Log file   : $effectiveLogFile"           -ForegroundColor White
if ($Mode -eq "optimize") {
    Write-Host "Top results: $Top"            -ForegroundColor White
    Write-Host "Run prefix : $RunNamePrefix"  -ForegroundColor White
} elseif ($RunName -ne "") {
    Write-Host "Run name   : $RunName"         -ForegroundColor White
}
if ($Symbol -ne "") {
    Write-Host "Symbol     : $Symbol"         -ForegroundColor White
}
if ($Smoke) {
    Write-Host "Smoke      : ON"              -ForegroundColor White
}
Write-Host ""

# ── Run ────────────────────────────────────────────────────────────────────────
Write-Host "[RUN] $Mode starting..." -ForegroundColor Green
Write-Host ""

& $PYTHON_EXE $targetScript @args_list
$exit_code = $LASTEXITCODE

Write-Host ""
if ($exit_code -eq 0) {
    Write-Host "[DONE] $Mode completed successfully." -ForegroundColor Green
} else {
    Write-Host "[FAIL] $Mode exited with code $exit_code." -ForegroundColor Red
}

Write-Host ""
Write-Host "Press Enter to exit..."
Read-Host | Out-Null
