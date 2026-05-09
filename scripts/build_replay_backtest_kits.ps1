#Requires -Version 5.1
param(
    [string]$Version = "v1",
    [string]$OutputRoot = "",
    [switch]$Clean,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ROOT = (Get-Item "$PSScriptRoot\..").FullName
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $ROOT "dist"
}

$platform = if ($env:OS -eq "Windows_NT") { "windows" } else { "unknown" }
$replayKitName = "astra-replay-kit-$Version-$platform"
$backtestKitName = "astra-backtest-kit-$Version-$platform"
$replayKitRoot = Join-Path $OutputRoot $replayKitName
$backtestKitRoot = Join-Path $OutputRoot $backtestKitName

$replayItems = @(
    @{ Source = "services\strategy_runtime"; Target = "services\strategy_runtime" },
    @{ Source = "services\replay_engine"; Target = "services\replay_engine" },
    @{ Source = "packages\trading_core"; Target = "packages\trading_core" },
    @{ Source = "scripts\start_strategy_runtime_paper_replay.ps1"; Target = "scripts\start_strategy_runtime_paper_replay.ps1" },
    @{ Source = "scripts\start_strategy_runtime_live_paper.ps1"; Target = "scripts\start_strategy_runtime_live_paper.ps1" },
    @{ Source = "scripts\authenticate_broker.py"; Target = "scripts\authenticate_broker.py" },
    @{ Source = "services\strategy_runtime\astra-kit-requirements.txt"; Target = "services\strategy_runtime\astra-kit-requirements.txt" },
    @{ Source = "config\strategy_runtime.paper_replay.env.example"; Target = "config\strategy_runtime.paper_replay.env.example" },
    @{ Source = "config\strategy_runtime.paper_replay.env"; Target = "config\strategy_runtime.paper_replay.env"; Optional = $true },
    @{ Source = "config\.env"; Target = "config\.env"; Optional = $true },
    @{ Source = "services\strategy_runtime\strategies\nifty_trend_options\STRATEGY.md"; Target = "services\strategy_runtime\strategies\nifty_trend_options\STRATEGY.md"; Optional = $true },
    @{ Source = "services\strategy_runtime\ARCHITECTURE_DIAGRAMS.md"; Target = "services\strategy_runtime\ARCHITECTURE_DIAGRAMS.md"; Optional = $true },
    @{ Source = "scripts\START_REPLAY_KIT.ps1"; Target = "START_REPLAY_KIT.ps1" }
)

$backtestItems = @(
    @{ Source = "scripts\strategy_backtest.py"; Target = "scripts\strategy_backtest.py" },
    @{ Source = "scripts\strategy_optimize.py"; Target = "scripts\strategy_optimize.py" },
    @{ Source = "services\strategy_runtime"; Target = "services\strategy_runtime" },
    @{ Source = "services\strategy_runtime\astra-kit-requirements.txt"; Target = "services\strategy_runtime\astra-kit-requirements.txt" },
    @{ Source = "packages\trading_core"; Target = "packages\trading_core" },
    @{ Source = "config\.env"; Target = "config\.env"; Optional = $true },
    @{ Source = "services\strategy_runtime\strategies\nifty_trend_options\STRATEGY.md"; Target = "docs\nifty_trend_options_STRATEGY.md"; Optional = $true },
    @{ Source = "Astra_UserGuide.md"; Target = "docs\Astra_UserGuide.md"; Optional = $true },
    @{ Source = "scripts\START_BACKTEST_KIT.ps1"; Target = "START_BACKTEST_KIT.ps1" }
)

function Ensure-Directory {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        New-Item -Path $Path -ItemType Directory -Force | Out-Null
    }
}

function Copy-ItemSafe {
    param(
        [string]$Source,
        [string]$Destination,
        [bool]$Optional = $false
    )

    if (-not (Test-Path $Source)) {
        if ($Optional) {
            Write-Host "[!] Skipping optional item: $Source"
            return
        }
        throw "Required source not found: $Source"
    }

    $destinationParent = Split-Path -Path $Destination -Parent
    Ensure-Directory -Path $destinationParent
    Copy-Item -Path $Source -Destination $Destination -Recurse -Force
}

function Write-KitManifest {
    param(
        [string]$Path,
        [string]$KitType,
        [string]$KitName,
        [object[]]$Items
    )

    $manifest = [ordered]@{
        generated_at = (Get-Date).ToString("s")
        kit_type = $KitType
        kit_name = $KitName
        version = $Version
        platform = $platform
        excludes = @("db_data", "db_backups", "logs")
        item_count = $Items.Count
        notes = @(
            "Database files are intentionally excluded.",
            "Point config/.env DATABASE_URL to your local running DB.",
            "Replay kit includes runtime + replay engine for paper replay runs."
        )
    }

    $manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $Path -Encoding UTF8
}

function Build-Kit {
    param(
        [string]$KitRoot,
        [string]$KitType,
        [string]$KitName,
        [object[]]$Items
    )

    if ($Clean -and (Test-Path $KitRoot)) {
        Write-Host "[*] Removing existing $KitType kit at $KitRoot"
        if (-not $DryRun) {
            Remove-Item -Path $KitRoot -Recurse -Force
        }
    }

    Write-Host "[*] Creating $KitType kit root at $KitRoot"
    if (-not $DryRun) {
        Ensure-Directory -Path $KitRoot
    }

    foreach ($item in $Items) {
        $source = Join-Path $ROOT $item.Source
        $destination = Join-Path $KitRoot $item.Target
        $optional = [bool]($item.Optional)

        Write-Host "[*] Copying $($item.Source) -> $($item.Target)"
        if (-not $DryRun) {
            Copy-ItemSafe -Source $source -Destination $destination -Optional $optional
        }
    }

    $manifestPath = Join-Path $KitRoot "kit-manifest.json"
    Write-Host "[*] Writing manifest for $KitType kit"
    if (-not $DryRun) {
        Write-KitManifest -Path $manifestPath -KitType $KitType -KitName $KitName -Items $Items
    }
}

Build-Kit -KitRoot $replayKitRoot -KitType "replay" -KitName $replayKitName -Items $replayItems
Build-Kit -KitRoot $backtestKitRoot -KitType "backtest" -KitName $backtestKitName -Items $backtestItems

Write-Host ""
Write-Host "Replay kit:   $replayKitRoot"
Write-Host "Backtest kit: $backtestKitRoot"
if ($DryRun) {
    Write-Host "Mode: dry-run only; no files were written."
}
