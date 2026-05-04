#Requires -Version 5.1
<#
.SYNOPSIS
    Astra Backtest Kit - Run NIFTY Trend Options backtest or parameter optimisation.

.DESCRIPTION
    Runs backtest_nifty_trend.py or optimize_nifty_trend.py against historical data
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

.EXAMPLE
    .\START_BACKTEST_KIT.ps1
    .\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28
    .\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28 -Mode optimize -Top 15
    .\START_BACKTEST_KIT.ps1 -From 2026-04-01 -To 2026-04-28 -Symbol "NSE_INDEX|Nifty 50"
#>
param(
    [string]$From   = "",
    [string]$To     = "",
    [ValidateSet("backtest", "optimize")]
    [string]$Mode   = "backtest",
    [int]$Top       = 10,
    [string]$Symbol = ""
)

$ErrorActionPreference = 'Stop'

# ── Resolve kit root ───────────────────────────────────────────────────────────
$KIT_ROOT    = $PSScriptRoot
$PYTHON_EXE  = "$KIT_ROOT\.venv\Scripts\python.exe"
$BACKTEST_PY = "$KIT_ROOT\scripts\backtest_nifty_trend.py"
$OPTIMIZE_PY = "$KIT_ROOT\scripts\optimize_nifty_trend.py"
$GLOBAL_ENV  = "$KIT_ROOT\config\.env"

# ── Banner ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "    Astra Backtest Kit - NIFTY Trend Options Analyser     " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

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
function Load-EnvFile([string]$Path) {
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
    Load-EnvFile $GLOBAL_ENV
    Write-Host "[INFO] Loaded credentials from config\.env" -ForegroundColor DarkGray
} else {
    Write-Host "[WARN] config\.env not found - DB connection may fail." -ForegroundColor Yellow
    Write-Host "       Create it with DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD." -ForegroundColor Yellow
}

# ── Set PYTHONPATH ─────────────────────────────────────────────────────────────
$env:PYTHONPATH = "$KIT_ROOT\packages\trading_core"

# ── Prompt for dates if not provided ──────────────────────────────────────────
if ($From -eq "") {
    $From = Read-Host "Enter start date [YYYY-MM-DD]"
}

if ($To -eq "") {
    $defaultTo = (Get-Date).ToString("yyyy-MM-dd")
    $input = Read-Host "Enter end date [YYYY-MM-DD] (default: $defaultTo)"
    $To = if ($input.Trim() -eq "") { $defaultTo } else { $input.Trim() }
}

# ── Validate date format ───────────────────────────────────────────────────────
$datePattern = '^\d{4}-\d{2}-\d{2}$'
if ($From -notmatch $datePattern -or $To -notmatch $datePattern) {
    Write-Host "[ERROR] Dates must be in YYYY-MM-DD format." -ForegroundColor Red
    exit 1
}

# ── Build argument list ────────────────────────────────────────────────────────
$args_list = @("--from", $From, "--to", $To)

if ($Symbol -ne "") {
    $args_list += @("--symbol", $Symbol)
}

if ($Mode -eq "optimize") {
    $args_list += @("--top", $Top)
}

# ── Print run summary ──────────────────────────────────────────────────────────
Write-Host "Mode       : $Mode"              -ForegroundColor White
Write-Host "Date range : $From -> $To"       -ForegroundColor White
if ($Mode -eq "optimize") {
    Write-Host "Top results: $Top"            -ForegroundColor White
}
if ($Symbol -ne "") {
    Write-Host "Symbol     : $Symbol"         -ForegroundColor White
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
