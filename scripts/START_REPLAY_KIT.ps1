#Requires -Version 5.1
<#
.SYNOPSIS
    Astra Replay Kit - One-click launcher for NIFTY Trend Options replay paper trading.

.DESCRIPTION
    Starts the replay engine and strategy runtime together using kit-local paths.
    Uses config/strategy_runtime.paper_replay.env for strategy settings.
    Prints a full preflight summary (config, paths, DB, expected behavior) before launch.
    Polls /status every 5 seconds and shows live color-coded progress while replay runs.
    Writes a per-run summary log to logs/run_summaries/.

.PARAMETER Strategy
    Strategy name to run. Default: nifty_trend_options

.PARAMETER Date
    Replay date (YYYY-MM-DD) to start from. If omitted, the env file value is used.

.PARAMETER SkipReplayEngine
    If set, only starts the strategy runtime (assumes replay engine is already running).

.PARAMETER ConfirmationMode
    interactive    -> prompt after preflight summary before launching runtime
    non-interactive -> do not prompt; continue automatically

.EXAMPLE
    .\START_REPLAY_KIT.ps1
    .\START_REPLAY_KIT.ps1 -Date 2026-04-15
    .\START_REPLAY_KIT.ps1 -Strategy nifty_trend_options -Date 2026-04-20
    .\START_REPLAY_KIT.ps1 -ConfirmationMode non-interactive
#>
param(
    [string]$Strategy = "nifty_trend_options",
    [string]$Date = "",
    [switch]$SkipReplayEngine,
    [ValidateSet("interactive", "non-interactive")]
    [string]$ConfirmationMode = "interactive"
)

$ErrorActionPreference = 'Stop'

# ── Resolve kit root ───────────────────────────────────────────────────────────
$KIT_ROOT    = $PSScriptRoot
$PYTHON_EXE  = "$KIT_ROOT\.venv\Scripts\python.exe"
$RUNTIME_SRV = "$KIT_ROOT\services\strategy_runtime\server.py"
$REPLAY_MAIN  = "$KIT_ROOT\services\replay_engine\main.py"
$ENV_FILE     = "$KIT_ROOT\config\strategy_runtime.paper_replay.env"
$GLOBAL_ENV   = "$KIT_ROOT\config\.env"
$LOG_DIR      = "$KIT_ROOT\logs"
$RUN_SUMMARY_DIR = "$LOG_DIR\run_summaries"
$RUN_ID = Get-Date -Format "yyyyMMdd_HHmmss"
$RUN_SUMMARY_FILE = "$RUN_SUMMARY_DIR\replay_run_${RUN_ID}.log"
$preflightRecordCount = -1
$RUNTIME_STDOUT_LOG = "$LOG_DIR\runtime_stdout.log"
$RUNTIME_STDERR_LOG = "$LOG_DIR\runtime_stderr.log"
$launchStartedAt = $null

# ── Banner ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Astra Replay Kit - NIFTY Trend Options Paper Replay    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# ── Pre-flight checks ──────────────────────────────────────────────────────────
if (-not (Test-Path $PYTHON_EXE)) {
    Write-Host "[ERROR] Python virtual environment not found at .venv\" -ForegroundColor Red
    Write-Host "        Run: python -m venv .venv" -ForegroundColor Yellow
    Write-Host "        Then: .venv\Scripts\pip install -e packages\trading_core" -ForegroundColor Yellow
    Write-Host "        Then: .venv\Scripts\pip install -r services\strategy_runtime\requirements.txt" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $RUNTIME_SRV)) {
    Write-Host "[ERROR] strategy_runtime server not found: $RUNTIME_SRV" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ENV_FILE)) {
    Write-Host "[WARN] Env file not found: $ENV_FILE" -ForegroundColor Yellow
    Write-Host "       Copying from example..." -ForegroundColor Yellow
    $example = "$KIT_ROOT\config\strategy_runtime.paper_replay.env.example"
    if (Test-Path $example) {
        Copy-Item $example $ENV_FILE
        Write-Host "       Created $ENV_FILE - please edit it before running." -ForegroundColor Green
        notepad.exe $ENV_FILE
        exit 0
    } else {
        Write-Host "[ERROR] No env file or example found. Cannot continue." -ForegroundColor Red
        exit 1
    }
}

# ── Helper functions ───────────────────────────────────────────────────────────
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

function Write-RunSummary([string]$Message, [string]$Color = "Gray") {
    Write-Host $Message -ForegroundColor $Color
    Add-Content -Path $RUN_SUMMARY_FILE -Value $Message -Encoding UTF8
}

function Get-ReplayTableName([string]$Provider, [string]$DataType) {
    $providerValue = if ([string]::IsNullOrWhiteSpace($Provider)) { "fyers" } else { $Provider }
    $p = $providerValue.ToLowerInvariant()
    $schema = if ($p -eq "upstox") { "broker_upstox" } else { "broker_fyers" }

    $dataTypeValue = if ([string]::IsNullOrWhiteSpace($DataType)) { "ohlcv_1m" } else { $DataType }
    switch ($dataTypeValue.ToLowerInvariant()) {
        "market_ticks"           { return "$schema.market_ticks" }
        "ohlcv_1m"               { return "$schema.ohlcv_1m" }
        "ohlcv_1min_from_ticks"  { return "$schema.ohlcv_1min_from_ticks" }
        "options_ohlc"           { return "$schema.options_ohlc" }
        default                  { return "$schema.<unknown_data_type>" }
    }
}

function Get-EnvOrDefault([string]$Name, [string]$Default = "") {
    $v = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ([string]::IsNullOrWhiteSpace($v)) { return $Default }
    return $v
}

function Get-RuntimeStatus([string]$BaseUrl = "http://localhost:8090") {
    try {
        return Invoke-RestMethod -Uri "$BaseUrl/status" -Method Get -TimeoutSec 5
    } catch {
        return $null
    }
}

function Write-ProgressSnapshot($Status) {
    if ($null -eq $Status) {
        Write-Host "[PROGRESS] Waiting for runtime status endpoint..." -ForegroundColor DarkGray
        return
    }

    $latestBarTime = "<pending>"
    $latestClose   = "<pending>"
    if ($null -ne $Status.latest_bar) {
        if ($Status.latest_bar.time)             { $latestBarTime = [string]$Status.latest_bar.time }
        if ($null -ne $Status.latest_bar.close)  { $latestClose   = [string]$Status.latest_bar.close }
    }

    $positionState = "flat"
    if ($null -ne $Status.position) {
        $positionState = "{0} qty={1} avg={2}" -f $Status.position.side, $Status.position.quantity, $Status.position.avg_price
    }

    $replayCompleted = $false
    $replayError     = $null
    if ($null -ne $Status.replay) {
        $replayCompleted = [bool]$Status.replay.completed
        $replayError     = $Status.replay.error
    }

    $state      = "running"
    $stateColor = "DarkCyan"
    if (-not [string]::IsNullOrWhiteSpace([string]$replayError)) {
        $state = "error";     $stateColor = "Red"
    } elseif ($replayCompleted) {
        $state = "completed"; $stateColor = "Green"
    } elseif ($latestBarTime -eq "<pending>") {
        $state = "idle";      $stateColor = "Yellow"
    }

    $progressLine = "[PROGRESS][{0}] latest_bar={1} close={2} position={3} completed={4}" -f `
        $state.ToUpperInvariant(), $latestBarTime, $latestClose, $positionState, $replayCompleted
    if (-not [string]::IsNullOrWhiteSpace([string]$replayError)) {
        $progressLine += " error=$replayError"
    }

    Write-Host $progressLine -ForegroundColor $stateColor
    Add-Content -Path $RUN_SUMMARY_FILE -Value $progressLine -Encoding UTF8
}

function Write-EndSummary($FinalStatus, [int]$ExitCode) {
    $endedAt      = Get-Date
    $durationText = "<unknown>"
    if ($null -ne $launchStartedAt) {
        $duration     = New-TimeSpan -Start $launchStartedAt -End $endedAt
        $durationText = $duration.ToString()
    }

    $latestBarTime   = "<none>"
    $latestClose     = "<none>"
    $positionText    = "flat"
    $replayCompleted = $false
    $replayError     = ""
    $lastError       = ""
    $running         = $false

    if ($null -ne $FinalStatus) {
        $running   = [bool]$FinalStatus.running
        $lastError = [string]$FinalStatus.last_error
        if ($null -ne $FinalStatus.latest_bar) {
            if ($FinalStatus.latest_bar.time)            { $latestBarTime = [string]$FinalStatus.latest_bar.time }
            if ($null -ne $FinalStatus.latest_bar.close) { $latestClose   = [string]$FinalStatus.latest_bar.close }
        }
        if ($null -ne $FinalStatus.position) {
            $positionText = "{0} qty={1} avg={2}" -f $FinalStatus.position.side, $FinalStatus.position.quantity, $FinalStatus.position.avg_price
        }
        if ($null -ne $FinalStatus.replay) {
            $replayCompleted = [bool]$FinalStatus.replay.completed
            $replayError     = [string]$FinalStatus.replay.error
        }
    }

    Write-RunSummary ""
    Write-RunSummary "[FINAL SUMMARY]" "Cyan"
    Write-RunSummary "  Launch Started At   : $(if ($launchStartedAt) { $launchStartedAt.ToString('s') } else { '<unknown>' })" "White"
    Write-RunSummary "  Launch Ended At     : $($endedAt.ToString('s'))" "White"
    Write-RunSummary "  Total Duration      : $durationText" "White"
    Write-RunSummary "  Runtime Exit Code   : $ExitCode" "White"
    Write-RunSummary "  Runtime Running     : $running" "White"
    Write-RunSummary "  Replay Completed    : $replayCompleted" "White"
    Write-RunSummary "  Last Replay Bar     : $latestBarTime" "White"
    Write-RunSummary "  Last Replay Close   : $latestClose" "White"
    Write-RunSummary "  Final Position      : $positionText" "White"
    Write-RunSummary "  Runtime Last Error  : $(if ($lastError) { $lastError } else { '<none>' })" "White"
    Write-RunSummary "  Replay Error        : $(if ($replayError) { $replayError } else { '<none>' })" "White"
    Write-RunSummary "  Runtime Stdout Log  : $RUNTIME_STDOUT_LOG" "White"
    Write-RunSummary "  Runtime Stderr Log  : $RUNTIME_STDERR_LOG" "White"
    Write-RunSummary "  Run Summary File    : $RUN_SUMMARY_FILE" "White"
    Write-RunSummary ""
}

# ── Load env files ─────────────────────────────────────────────────────────────
if (Test-Path $GLOBAL_ENV) { Load-EnvFile $GLOBAL_ENV }
Load-EnvFile $ENV_FILE

# Override date if supplied via param
if ($Date -ne "") {
    [Environment]::SetEnvironmentVariable("REPLAY_START_DATE", $Date, 'Process')
    Write-Host "[INFO] Replay date overridden to: $Date" -ForegroundColor Cyan
}

# Force strategy
[Environment]::SetEnvironmentVariable("STRATEGY_NAME", $Strategy, 'Process')

# Set PYTHONPATH to include kit-local packages
$env:PYTHONPATH = "$KIT_ROOT;$KIT_ROOT\packages\trading_core"

# ── Create log directories ─────────────────────────────────────────────────────
if (-not (Test-Path $LOG_DIR))          { New-Item -ItemType Directory -Path $LOG_DIR          | Out-Null }
if (-not (Test-Path $RUN_SUMMARY_DIR))  { New-Item -ItemType Directory -Path $RUN_SUMMARY_DIR  | Out-Null }

"=== Astra Replay Run Summary ===" | Set-Content -Path $RUN_SUMMARY_FILE -Encoding UTF8
Add-Content -Path $RUN_SUMMARY_FILE -Value "GeneratedAt: $((Get-Date).ToString('s'))"
Add-Content -Path $RUN_SUMMARY_FILE -Value "RunId: $RUN_ID"
Add-Content -Path $RUN_SUMMARY_FILE -Value ""

# ── Resolve and display config ─────────────────────────────────────────────────
$replayDate  = [Environment]::GetEnvironmentVariable("REPLAY_START_DATE", 'Process')
$replaySpeed = Get-EnvOrDefault "STRATEGY_RUNTIME_REPLAY_SPEED" "5"

$feedSrc = [Environment]::GetEnvironmentVariable("STRATEGY_RUNTIME_FEED_SOURCE", 'Process')
if ([string]::IsNullOrWhiteSpace($feedSrc)) {
    $feedSrc = [Environment]::GetEnvironmentVariable("FEED_SOURCE", 'Process')
}

$provider    = Get-EnvOrDefault "STRATEGY_RUNTIME_PROVIDER"          "fyers"
$symbol      = Get-EnvOrDefault "STRATEGY_RUNTIME_SYMBOL"            ""
$dataType    = Get-EnvOrDefault "STRATEGY_RUNTIME_REPLAY_DATA_TYPE"  "ohlcv_1m"
$timeframe   = Get-EnvOrDefault "STRATEGY_RUNTIME_TIMEFRAME"         "1m"
$indicatorMode = Get-EnvOrDefault "STRATEGY_RUNTIME_INDICATOR_INPUT_MODE" "bars_1m"
$dataTypeLower = if ([string]::IsNullOrWhiteSpace($dataType)) { "" } else { $dataType.ToLowerInvariant() }
$indicatorModeLower = if ([string]::IsNullOrWhiteSpace($indicatorMode)) { "" } else { $indicatorMode.ToLowerInvariant() }
$preflightTimeframe = if ($dataTypeLower -eq "market_ticks" -and $indicatorModeLower -eq "bars_1m") { "1m" } else { $timeframe }
$tableName   = Get-ReplayTableName -Provider $provider -DataType $dataType
$replayWsUrl = Get-EnvOrDefault "STRATEGY_RUNTIME_REPLAY_WS_URL"     "ws://localhost:8765"
$startTime   = Get-EnvOrDefault "STRATEGY_RUNTIME_REPLAY_START_TIME" ""
$endTime     = Get-EnvOrDefault "STRATEGY_RUNTIME_REPLAY_END_TIME"   ""

$dbHost = Get-EnvOrDefault "DB_HOST" ""
$dbPort = Get-EnvOrDefault "DB_PORT" ""
$dbName = Get-EnvOrDefault "DB_NAME" ""
$dbUser = Get-EnvOrDefault "DB_USER" ""

if ([string]::IsNullOrWhiteSpace($dbHost) -or [string]::IsNullOrWhiteSpace($dbName)) {
    $dbUrl = Get-EnvOrDefault "DATABASE_URL" ""
    if (-not [string]::IsNullOrWhiteSpace($dbUrl)) {
        try {
            $uri = [System.Uri]$dbUrl
            if ([string]::IsNullOrWhiteSpace($dbHost)) { $dbHost = $uri.Host }
            if ([string]::IsNullOrWhiteSpace($dbPort)) { $dbPort = [string]$uri.Port }
            if ([string]::IsNullOrWhiteSpace($dbName)) { $dbName = $uri.AbsolutePath.TrimStart('/') }
            if ([string]::IsNullOrWhiteSpace($dbUser) -and -not [string]::IsNullOrWhiteSpace($uri.UserInfo)) {
                $dbUser = ($uri.UserInfo -split ':', 2)[0]
            }
        } catch {
            # Keep values blank if DATABASE_URL cannot be parsed as URI.
        }
    }
}

Write-Host "Strategy  : $Strategy"        -ForegroundColor White
Write-Host "Replay Date: $replayDate"     -ForegroundColor White
Write-Host "Speed      : ${replaySpeed}x" -ForegroundColor White
Write-Host "Feed Source: $feedSrc"        -ForegroundColor White
Write-Host "Log Dir    : $LOG_DIR"        -ForegroundColor White
Write-Host ""

Write-RunSummary "[CONFIG]"
Write-RunSummary "  Strategy            : $Strategy"                                                    "White"
Write-RunSummary "  Feed Source         : $feedSrc"                                                     "White"
Write-RunSummary "  Provider            : $provider"                                                    "White"
Write-RunSummary "  Symbol              : $symbol"                                                      "White"
Write-RunSummary "  Timeframe           : $timeframe"                                                   "White"
Write-RunSummary "  Replay Data Type    : $dataType"                                                    "White"
Write-RunSummary "  Indicator Input Mode: $indicatorMode"                                               "White"
Write-RunSummary "  Preflight Timeframe : $preflightTimeframe"                                           "White"
Write-RunSummary "  Replay Speed        : ${replaySpeed}x"                                              "White"
Write-RunSummary "  Replay Start Time   : $(if ($startTime) { $startTime } else { '<not set>' })"       "White"
Write-RunSummary "  Replay End Time     : $(if ($endTime)   { $endTime   } else { '<not set>' })"       "White"
Write-RunSummary "  Replay WS URL       : $replayWsUrl"                                                 "White"
Write-RunSummary ""
Write-RunSummary "[PATHS]"
Write-RunSummary "  Kit Root            : $KIT_ROOT"           "White"
Write-RunSummary "  Python Exe          : $PYTHON_EXE"         "White"
Write-RunSummary "  Runtime Server      : $RUNTIME_SRV"        "White"
Write-RunSummary "  Replay Engine Main  : $REPLAY_MAIN"        "White"
Write-RunSummary "  Strategy Env File   : $ENV_FILE"           "White"
Write-RunSummary "  Global Env File     : $GLOBAL_ENV"         "White"
Write-RunSummary "  Log Dir             : $LOG_DIR"            "White"
Write-RunSummary "  Run Summary File    : $RUN_SUMMARY_FILE"   "White"
Write-RunSummary "  Runtime Stdout Log  : $RUNTIME_STDOUT_LOG" "White"
Write-RunSummary "  Runtime Stderr Log  : $RUNTIME_STDERR_LOG" "White"
Write-RunSummary "  Confirmation Mode   : $ConfirmationMode"   "White"
Write-RunSummary ""
Write-RunSummary "[DATABASE]"
Write-RunSummary "  Host                : $(if ($dbHost) { $dbHost } else { '<unknown>' })"   "White"
Write-RunSummary "  Port                : $(if ($dbPort) { $dbPort } else { '<unknown>' })"   "White"
Write-RunSummary "  Name                : $(if ($dbName) { $dbName } else { '<unknown>' })"   "White"
Write-RunSummary "  User                : $(if ($dbUser) { $dbUser } else { '<unknown>' })"   "White"
Write-RunSummary "  Replay Source Table : $tableName"                                          "White"
Write-RunSummary ""
Write-RunSummary "[EXPECTED BEHAVIOR]"
Write-RunSummary "  1) Replay engine loads historical bars from the replay source table."                           "White"
Write-RunSummary "  2) Strategy runtime consumes bars via WebSocket and updates latest_bar in /status."            "White"
Write-RunSummary "  3) If strategy signals trigger, paper orders/fills appear in journal logs."                    "White"
Write-RunSummary "  4) When replay reaches end, replay.completed becomes true and runtime loop exits cleanly."     "White"
Write-RunSummary ""

# ── Start replay engine ────────────────────────────────────────────────────────
if (-not $SkipReplayEngine) {
    if (-not (Test-Path $REPLAY_MAIN)) {
        Write-Host "[WARN] Replay engine not found at $REPLAY_MAIN - skipping." -ForegroundColor Yellow
    } else {
        Write-Host "[1/2] Starting replay engine..." -ForegroundColor Green
        $replayLog = "$LOG_DIR\replay_engine.log"
        $replayProc = Start-Process -FilePath $PYTHON_EXE `
            -ArgumentList $REPLAY_MAIN `
            -WorkingDirectory "$KIT_ROOT\services\replay_engine" `
            -PassThru `
            -NoNewWindow `
            -RedirectStandardOutput $replayLog `
            -RedirectStandardError  "$LOG_DIR\replay_engine_err.log"

        Write-Host "       PID $($replayProc.Id) | log: $replayLog" -ForegroundColor DarkGray
        Write-Host "       Waiting 3s for replay engine to initialise..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 3

        if ($replayProc.HasExited) {
            Write-Host "[ERROR] Replay engine exited early. Check $LOG_DIR\replay_engine_err.log" -ForegroundColor Red
            Write-RunSummary "[ERROR] Replay engine exited early. See: $LOG_DIR\replay_engine_err.log" "Red"
            exit 1
        }
    }
}

# ── Replay preflight data check ───────────────────────────────────────────────
Write-RunSummary "[PREFLIGHT] Checking replay data availability..." "Cyan"
try {
    $uriBuilder = New-Object System.Text.StringBuilder
    [void]$uriBuilder.Append("http://localhost:8766/replay/load?")
    [void]$uriBuilder.Append("symbol=").Append([uri]::EscapeDataString($symbol))
    [void]$uriBuilder.Append("&provider=").Append([uri]::EscapeDataString($provider))
    [void]$uriBuilder.Append("&data_type=").Append([uri]::EscapeDataString($dataType))
    [void]$uriBuilder.Append("&timeframe=").Append([uri]::EscapeDataString($preflightTimeframe))
    if (-not [string]::IsNullOrWhiteSpace($startTime)) {
        [void]$uriBuilder.Append("&start_time=").Append([uri]::EscapeDataString($startTime))
    }
    if (-not [string]::IsNullOrWhiteSpace($endTime)) {
        [void]$uriBuilder.Append("&end_time=").Append([uri]::EscapeDataString($endTime))
    }

    $preflightUrl  = $uriBuilder.ToString()
    $preflightResp = Invoke-RestMethod -Uri $preflightUrl -Method Get -TimeoutSec 20
    $count         = [int]($preflightResp.record_count)
    $preflightRecordCount = $count

    Write-RunSummary "  Preflight URL       : $preflightUrl" "DarkGray"
    Write-RunSummary "  Replay Record Count : $count"         "White"

    if ($count -le 0) {
        Write-RunSummary "  [WARN] No replay rows found for current symbol/provider/time window." "Yellow"
        Write-RunSummary "         Runtime may stay idle with latest_bar=null until config is corrected." "Yellow"
    } else {
        $speedFloat = 1.0
        if (-not [double]::TryParse([string]$replaySpeed, [ref]$speedFloat) -or $speedFloat -le 0) {
            $speedFloat = 1.0
        }
        $etaSeconds = [int][math]::Ceiling($count / $speedFloat)
        Write-RunSummary "  Estimated Replay Duration (s): $etaSeconds" "White"
        Write-RunSummary "  Expected: /status latest_bar should advance and logs/journal should grow." "Green"
    }
} catch {
    Write-RunSummary "  [WARN] Preflight check failed: $($_.Exception.Message)" "Yellow"
    if ($_.Exception.Response -ne $null) {
        try {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $body = $reader.ReadToEnd()
            if (-not [string]::IsNullOrWhiteSpace($body)) {
                Write-RunSummary "  [WARN] Preflight response body: $body" "Yellow"
            }
        } catch {
            # Ignore body parsing failures.
        }
    }
    Write-RunSummary "         Ensure replay engine HTTP API is reachable at http://localhost:8766/replay/load" "Yellow"
}
Write-RunSummary ""

# ── Confirmation gate ──────────────────────────────────────────────────────────
if ($ConfirmationMode -eq "interactive") {
    Write-RunSummary "[CONFIRM] Review the details above before starting replay runtime." "Cyan"
    if ($preflightRecordCount -eq 0) {
        Write-RunSummary "          Warning: preflight found 0 replay rows for the current query." "Yellow"
    }
    Write-Host ""
    $answer     = Read-Host "Proceed with replay launch? [Y/N]"
    $normalizedInput = if ($null -eq $answer) { "" } else { [string]$answer }
    $normalized = $normalizedInput.Trim().ToLowerInvariant()
    if ($normalized -notin @("y", "yes")) {
        Write-RunSummary "[ABORT] Launch cancelled by user after preflight review." "Yellow"
        Write-Host "[INFO] Launch cancelled." -ForegroundColor Yellow
        exit 0
    }
    Write-RunSummary "[CONFIRM] User accepted launch; continuing." "Green"
} else {
    Write-RunSummary "[CONFIRM] Non-interactive mode selected; continuing without prompt." "Cyan"
}
Write-RunSummary ""

# ── Start strategy runtime ─────────────────────────────────────────────────────
Write-Host "[2/2] Starting strategy runtime ($Strategy)..." -ForegroundColor Green
Write-Host "      Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""
Write-RunSummary "[START] Launching strategy runtime..." "Cyan"

try {
    Push-Location $KIT_ROOT
    $launchStartedAt = Get-Date
    $runtimeProc = Start-Process -FilePath $PYTHON_EXE `
        -ArgumentList $RUNTIME_SRV `
        -WorkingDirectory $KIT_ROOT `
        -PassThru `
        -NoNewWindow `
        -RedirectStandardOutput $RUNTIME_STDOUT_LOG `
        -RedirectStandardError  $RUNTIME_STDERR_LOG

    Write-RunSummary "[START] Strategy runtime PID $($runtimeProc.Id)" "Green"
    Write-RunSummary "[START] Polling http://localhost:8090/status every 5 seconds for live progress." "Cyan"

    $lastSnapshotKey = ""
    $lastStatus      = $null
    while (-not $runtimeProc.HasExited) {
        $status = Get-RuntimeStatus
        if ($null -ne $status) {
            $lastStatus   = $status
            $snapshotKey  = "{0}|{1}|{2}" -f [string]($status.latest_bar.time), [string]($status.replay.completed), [string]($status.position.quantity)
            if ($snapshotKey -ne $lastSnapshotKey) {
                Write-ProgressSnapshot -Status $status
                $lastSnapshotKey = $snapshotKey
            }
        } else {
            Write-ProgressSnapshot -Status $null
        }
        Start-Sleep -Seconds 5
    }

    $finalStatus = Get-RuntimeStatus
    if ($null -eq $finalStatus) { $finalStatus = $lastStatus }

    Write-RunSummary "[END] Strategy runtime exited with code $($runtimeProc.ExitCode)" "Cyan"
    Write-EndSummary -FinalStatus $finalStatus -ExitCode $runtimeProc.ExitCode

} finally {
    Pop-Location
    if ($null -ne $runtimeProc -and -not $runtimeProc.HasExited) {
        Write-RunSummary "[STOP] Stopping strategy runtime PID $($runtimeProc.Id)" "Yellow"
        Stop-Process -Id $runtimeProc.Id -Force -ErrorAction SilentlyContinue
    }
    if (-not $SkipReplayEngine -and $null -ne $replayProc -and -not $replayProc.HasExited) {
        Write-Host ""
        Write-Host "[INFO] Stopping replay engine (PID $($replayProc.Id))..." -ForegroundColor Yellow
        Write-RunSummary "[STOP] Stopping replay engine PID $($replayProc.Id)" "Yellow"
        Stop-Process -Id $replayProc.Id -Force -ErrorAction SilentlyContinue
    }
    Write-RunSummary "[END] Replay kit stopped." "Cyan"
    Write-Host "[INFO] Replay kit stopped." -ForegroundColor Cyan
}
