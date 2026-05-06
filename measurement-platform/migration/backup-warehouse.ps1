# backup-warehouse.ps1
# Nightly Postgres backup to Google Drive via rclone.
# Scheduled by Windows Task Scheduler at 3am (see MIGRATION_RUNBOOK.md Step 9).
#
# Retention policy applied here:
#   - Keep all daily backups for the last 14 days
#   - Keep weekly backups (Sunday) for the last 12 weeks
#   - Keep monthly backups (1st of month) forever
# rclone applies the cleanup; this script just creates new dumps.

$ErrorActionPreference = "Continue"
$logDir = "$HOME\backups\logs"
$dumpDir = "$HOME\backups\dumps"
New-Item -ItemType Directory -Path $logDir, $dumpDir -Force | Out-Null

$timestamp = Get-Date -Format "yyyy-MM-dd-HHmm"
$logFile = "$logDir\backup-$timestamp.log"

function Log($msg) {
    "$(Get-Date -Format 'HH:mm:ss')  $msg" | Tee-Object -FilePath $logFile -Append
}

Log "=== Backup starting ==="

# --- 1. pg_dump (custom format = compressed, parallel-restorable) ---
$dumpFile = "$dumpDir\analytics-$timestamp.dump"
$pgDump = "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"

# Read DB password from secure source. Prefer Windows Credential Manager or a .pgpass file.
# Quick path: store in env var via setx (one-time setup):
#   setx PGPASSWORD "<your-app-pw>" /M     (run once as admin)
if (-not $env:PGPASSWORD) {
    $pwFile = "$HOME\.openclaw\credentials\analytics-postgres-superuser-password.txt"
    if (Test-Path $pwFile) {
        $env:PGPASSWORD = (Get-Content $pwFile).Trim()
    } else {
        Log "ERROR: PGPASSWORD env var not set and credential file not found. Cannot dump."
        exit 1
    }
}

Log "Dumping analytics database..."
& $pgDump -U postgres -h localhost -d analytics --format=custom --file=$dumpFile 2>&1 | Tee-Object -Append $logFile

if (-not (Test-Path $dumpFile)) {
    Log "ERROR: dump file not created"
    exit 1
}

$dumpSize = [math]::Round((Get-Item $dumpFile).Length / 1MB, 2)
Log "Dump complete: $dumpFile ($dumpSize MB)"

# --- 2. Upload to Drive ---
Log "Uploading to Google Drive via rclone..."
rclone mkdir "gdrive-crypt:daily/" --log-file=$logFile --log-level INFO
rclone mkdir "gdrive-crypt:weekly/" --log-file=$logFile --log-level INFO
rclone mkdir "gdrive-crypt:monthly/" --log-file=$logFile --log-level INFO
rclone copy $dumpFile "gdrive-crypt:daily/" --log-file=$logFile --log-level INFO

# Tag this dump as weekly if Sunday
if ((Get-Date).DayOfWeek -eq "Sunday") {
    Log "Sunday - also tagging as weekly..."
    rclone copy $dumpFile "gdrive-crypt:weekly/" --log-file=$logFile --log-level INFO
}

# Tag as monthly if 1st of month
if ((Get-Date).Day -eq 1) {
    Log "1st of month - also tagging as monthly..."
    rclone copy $dumpFile "gdrive-crypt:monthly/" --log-file=$logFile --log-level INFO
}

# --- 3. Apply retention ---
Log "Pruning old backups..."

# Daily: keep 14 days
rclone delete "gdrive-crypt:daily/" --min-age 14d --log-file=$logFile

# Weekly: keep 84 days (12 weeks)
rclone delete "gdrive-crypt:weekly/" --min-age 84d --log-file=$logFile

# Monthly: kept forever - no prune

# Local dumps: keep last 7 only (save disk)
Get-ChildItem $dumpDir -Filter "*.dump" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 7 |
    Remove-Item -Force

# --- 4. Optional: Slack alert on failure ---
# Uncomment if you have SLACK_BOT_TOKEN set in machine env vars
# if ($LASTEXITCODE -ne 0) {
#     $payload = @{ channel = "C0AEXRYPA9Y"; text = ":warning: Warehouse backup FAILED at $timestamp - see $logFile" } | ConvertTo-Json
#     Invoke-RestMethod -Uri "https://slack.com/api/chat.postMessage" `
#         -Method Post -Headers @{ Authorization = "Bearer $env:SLACK_BOT_TOKEN" } `
#         -ContentType "application/json; charset=utf-8" -Body $payload
# }

Log "=== Backup complete ==="
