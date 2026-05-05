# stop-airbyte.ps1 — Stop Docker Desktop and kill WSL to reclaim RAM
# Run after syncs complete, or schedule 4 hours after start-airbyte-sync.ps1

$ErrorActionPreference = "Continue"
$logFile = "$HOME\.airbyte\sync-log-$(Get-Date -Format 'yyyy-MM-dd').txt"

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Tee-Object -FilePath $logFile -Append
}

Log "Stopping Docker Desktop..."
Stop-Process -Name "Docker Desktop" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 5

Log "Shutting down WSL (kills vmmem)..."
wsl --shutdown

Log "Docker and WSL stopped. RAM reclaimed."
