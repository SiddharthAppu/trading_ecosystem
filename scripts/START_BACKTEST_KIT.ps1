#Requires -Version 5.1
<#
.SYNOPSIS
    Astra Backtest Kit - Run strategy backtest or parameter optimisation.

.DESCRIPTION
    Runs strategy_backtest.py or strategy_optimize.py against historical data
    in TimescaleDB. Prompts for a date range if not supplied via parameters.
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
    Runs a quick adapter backtest smoke check (forces Mode=backtest, Engine=adapter,
    and auto-generates a run name when not provided).

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
    [ValidateSet("legacy", "adapter")]
    [string]$Engine = "legacy",
    [int]$Top       = 10,
    [string]$StrategyName = "nifty_trend_options",
    [string]$Timeframe = "5m",
    [string]$LogFile = "logs/strategy_runtime/runtime.log",
    [string]$RunName = "",
    [string]$RunNamePrefix = "opt",
    [switch]$Smoke,
    [string]$Symbol = "",
    [string]$EnvFile = ""
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
$GLOBAL_ENV  = if ($EnvFile) { if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $KIT_ROOT $EnvFile } } else { "$KIT_ROOT\config\.env" }

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
    if ($Engine -ne "adapter") {
        Write-Host "[INFO] Smoke mode forcing Engine=adapter" -ForegroundColor DarkGray
        $Engine = "adapter"
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
    Write-Host "        Then: .venv\Scripts\pip install asyncpg pandas python-dotenv" -ForegroundColor Yellow
    exit 1
}

$targetScript = if ($Mode -eq "optimize") { $OPTIMIZE_PY } else { $BACKTEST_PY }
if (-not (Test-Path $targetScript)) {
    Write-Host "[ERROR] Script not found: $targetScript" -ForegroundColor Red
    exit 1
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

if (Test-Path $GLOBAL_ENV) {
    Import-EnvFile $GLOBAL_ENV
    Write-Host "[INFO] Loaded credentials from $GLOBAL_ENV" -ForegroundColor DarkGray
} else {
    Write-Host "[WARN] Env file not found: $GLOBAL_ENV" -ForegroundColor Yellow
    Write-Host "       DB connection may fail if credentials are missing." -ForegroundColor Yellow
}

# ── Set PYTHONPATH ─────────────────────────────────────────────────────────────
$env:PYTHONPATH = "$KIT_ROOT\packages\trading_core"

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
$datePattern = '^\d{4}-\d{2}-\d{2}$'
if ($From -notmatch $datePattern -or $To -notmatch $datePattern) {
    Write-Host "[ERROR] Dates must be in YYYY-MM-DD format." -ForegroundColor Red
    exit 1
}

# ── Build argument list ────────────────────────────────────────────────────────
$args_list = @("--from", $From, "--to", $To)

$args_list += @(
    "--engine", $Engine,
    "--strategy-name", $StrategyName,
    "--timeframe", $Timeframe,
    "--log-file", $LogFile
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
Write-Host "Engine     : $Engine"            -ForegroundColor White
Write-Host "Date range : $From -> $To"       -ForegroundColor White
Write-Host "Strategy   : $StrategyName"      -ForegroundColor White
Write-Host "Timeframe  : $Timeframe"         -ForegroundColor White
Write-Host "Log file   : $LogFile"           -ForegroundColor White
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
