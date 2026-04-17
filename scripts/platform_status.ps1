#Requires -Version 5.1
param()

$ErrorActionPreference = 'SilentlyContinue'

Write-Host ""
Write-Host "============================================================"
Write-Host "  PLATFORM STATUS"
Write-Host "============================================================"

# Define services with their ports
$services = @(
    @{ Name = 'Data Collector';   Port = 8080; Label = 'data_collector' },
    @{ Name = 'Replay Engine';    Port = 8765; Label = 'replay_engine' },
    @{ Name = 'Historical UI';    Port = 3000; Label = 'historical_ui' },
    @{ Name = 'Forge UI';         Port = 3001; Label = 'forge_ui' }
)

foreach ($svc in $services) {
    $conn = Get-NetTCPConnection -LocalPort $svc.Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        $procName = if ($proc) { $proc.ProcessName } else { '?' }
        $procPath = if ($proc) {
            try { $proc.MainModule.FileName }
            catch { '(access denied)' }
        } else { '?' }
        
        $status = "[RUNNING] " + $svc.Name.PadRight(18) + " port=$($svc.Port)  pid=$($conn.OwningProcess)  process=$procName"
        Write-Host $status
        Write-Host ("          path: $procPath")
    } else {
        $status = "[STOPPED] " + $svc.Name.PadRight(18) + " port=$($svc.Port)"
        Write-Host $status
    }
}

Write-Host ""
Write-Host "---- Docker / TimescaleDB ----"
$dockerStatus = docker inspect -f '{{.State.Status}} (health={{.State.Health.Status}})' trading_timescaledb 2>$null
if ($dockerStatus) {
    Write-Host "[DB     ] TimescaleDB   $dockerStatus"
} else {
    Write-Host "[DB     ] TimescaleDB   container not found"
}

Write-Host ""
Write-Host "============================================================"
