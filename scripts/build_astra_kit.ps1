#Requires -Version 5.1
param(
    [string]$Version = "dev",
    [string]$OutputRoot = "",
    [string]$PythonExe = "",
    [switch]$IncludeWheelhouse,
    [switch]$Clean,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ROOT = (Get-Item "$PSScriptRoot\..").FullName
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $ROOT "dist"
}
if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = Join-Path $ROOT ".venv\Scripts\python.exe"
}

$platform = if ($env:OS -eq "Windows_NT") { "windows" } else { "unknown" }
$kitName = "astra-kit-$Version-$platform"
$kitRoot = Join-Path $OutputRoot $kitName
$wheelhouseDir = Join-Path $kitRoot "wheelhouse"
$requirementsFile = Join-Path $ROOT "services\strategy_runtime\astra-kit-requirements.txt"

$copyItems = @(
    @{ Source = "services\strategy_runtime"; Target = "services\strategy_runtime" },
    @{ Source = "packages\trading_core"; Target = "packages\trading_core" },
    @{ Source = "config\strategy_runtime.paper_replay.env.example"; Target = "config\strategy_runtime.paper_replay.env.example" },
    @{ Source = "config\strategy_runtime.paper_live.env.example"; Target = "config\strategy_runtime.paper_live.env.example" },
    @{ Source = "config\strategy_runtime.paper_live.env"; Target = "config\strategy_runtime.paper_live.env"; Optional = $true },
    @{ Source = "config\strategy_runtime.paper_replay.env"; Target = "config\strategy_runtime.paper_replay.env"; Optional = $true },
    @{ Source = "config\strategy_runtime.ema_cross.paper_replay.env"; Target = "config\strategy_runtime.ema_cross.paper_replay.env"; Optional = $true },
    @{ Source = "scripts\start_strategy_runtime_paper_replay.ps1"; Target = "scripts\start_strategy_runtime_paper_replay.ps1" },
    @{ Source = "scripts\start_strategy_runtime_live_paper.ps1"; Target = "scripts\start_strategy_runtime_live_paper.ps1" },
    @{ Source = "scripts\start_upstox_tick_capture_file.ps1"; Target = "scripts\start_upstox_tick_capture_file.ps1" },
    @{ Source = "scripts\authenticate_broker.py"; Target = "scripts\authenticate_broker.py" },
    @{ Source = "scripts\lib\quick_live_recorder.py"; Target = "scripts\lib\quick_live_recorder.py" },
    @{ Source = "services\strategy_runtime\astra-kit-requirements.txt"; Target = "services\strategy_runtime\astra-kit-requirements.txt" },
    @{ Source = "Astra_LLD.md"; Target = "docs\Astra_LLD.md" },
    @{ Source = "Astra_Requirements.md"; Target = "docs\Astra_Requirements.md" },
    @{ Source = "Astra_Requirements_v1.md"; Target = "docs\Astra_Requirements_v1.md" },
    @{ Source = "Astra_UserGuide.md"; Target = "docs\Astra_UserGuide.md" }
)

function Invoke-Step {
    param(
        [string]$Description,
        [scriptblock]$Action
    )

    Write-Host "[*] $Description"
    if ($DryRun) {
        return
    }
    & $Action
}

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

function Write-Manifest {
    param([string]$Path)

    $manifest = [ordered]@{
        generated_at = (Get-Date).ToString("s")
        version = $Version
        platform = $platform
        python = $PythonExe
        include_wheelhouse = [bool]$IncludeWheelhouse
        dry_run = [bool]$DryRun
        notes = @(
            "Broker auth tokens are intentionally not bundled.",
            "Use OS-matched builds for native dependencies such as TA-Lib.",
            "Prefer Python 3.11 or 3.12 for the first production TA-Lib kit."
        )
    }
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $Path -Encoding UTF8
}

if ($Clean -and (Test-Path $kitRoot)) {
    Invoke-Step -Description "Removing existing kit directory $kitRoot" -Action {
        Remove-Item -Path $kitRoot -Recurse -Force
    }
}

Invoke-Step -Description "Creating kit root at $kitRoot" -Action {
    Ensure-Directory -Path $kitRoot
}

foreach ($item in $copyItems) {
    $source = Join-Path $ROOT $item.Source
    $destination = Join-Path $kitRoot $item.Target
    $optional = [bool]($item.Optional)
    Invoke-Step -Description "Copying $($item.Source) -> $($item.Target)" -Action {
        Copy-ItemSafe -Source $source -Destination $destination -Optional $optional
    }
}

$manifestPath = Join-Path $kitRoot "astra-kit-manifest.json"
Invoke-Step -Description "Writing kit manifest" -Action {
    Write-Manifest -Path $manifestPath
}

if ($IncludeWheelhouse) {
    if (-not (Test-Path $PythonExe)) {
        throw "Python executable not found: $PythonExe"
    }

    Invoke-Step -Description "Creating wheelhouse directory" -Action {
        Ensure-Directory -Path $wheelhouseDir
    }

    Invoke-Step -Description "Downloading wheels into wheelhouse from $requirementsFile" -Action {
        & $PythonExe -m pip download -r $requirementsFile -d $wheelhouseDir
        if ($LASTEXITCODE -ne 0) {
            throw "pip download failed with exit code $LASTEXITCODE"
        }
    }
}

Write-Host ""
Write-Host "Astra kit build complete."
Write-Host "Kit root: $kitRoot"
if ($DryRun) {
    Write-Host "Mode: dry-run only; no files were written."
}
elseif ($IncludeWheelhouse) {
    Write-Host "Wheelhouse: $wheelhouseDir"
}
