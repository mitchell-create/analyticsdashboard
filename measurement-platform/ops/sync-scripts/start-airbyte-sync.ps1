# start-airbyte-sync.ps1 — Start Docker, wait for Airbyte, trigger all enabled syncs, run dbt
# Scheduled via Windows Task Scheduler for 2am on the 13th and 31st (or last day) of each month.

$ErrorActionPreference = "Continue"
$logFile = "$HOME\.airbyte\sync-log-$(Get-Date -Format 'yyyy-MM-dd').txt"

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Tee-Object -FilePath $logFile -Append
}

# --- 1. Start Docker Desktop ---
Log "Starting Docker Desktop..."
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

# Wait for Docker to be ready (up to 3 minutes)
$maxWait = 180
$waited = 0
while ($waited -lt $maxWait) {
    try {
        $result = docker ps 2>&1
        if ($LASTEXITCODE -eq 0) {
            Log "Docker is ready."
            break
        }
    } catch {}
    Start-Sleep -Seconds 10
    $waited += 10
    Log "Waiting for Docker... ($waited s)"
}

if ($waited -ge $maxWait) {
    Log "ERROR: Docker did not start within $maxWait seconds. Aborting."
    exit 1
}

# --- 2. Start Airbyte (kind cluster) ---
Log "Checking Airbyte status..."
$abctl = "$HOME\abctl-v0.30.4-windows-amd64\abctl-v0.30.4-windows-amd64\abctl.exe"
& $abctl local status 2>&1 | Out-String | Tee-Object -FilePath $logFile -Append

# Wait for Airbyte web UI to be ready (up to 10 minutes)
$maxWait = 600
$waited = 0
while ($waited -lt $maxWait) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000" -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Log "Airbyte is ready."
            break
        }
    } catch {}
    Start-Sleep -Seconds 15
    $waited += 15
    Log "Waiting for Airbyte UI... ($waited s)"
}

if ($waited -ge $maxWait) {
    Log "ERROR: Airbyte did not become ready within $maxWait seconds. Aborting."
    exit 1
}

# --- 3. Trigger all enabled connection syncs via Airbyte API ---
Log "Triggering all enabled connection syncs..."

# Get Airbyte credentials
$credOutput = & $abctl local credentials 2>&1 | Out-String
Log $credOutput

# Use default Airbyte local API (no auth required for OSS)
$baseUrl = "http://localhost:8000/api/v1"

try {
    # List all connections
    $connections = Invoke-RestMethod -Uri "$baseUrl/connections/list" -Method Post `
        -ContentType "application/json" `
        -Body '{"workspaceId":"00000000-0000-0000-0000-000000000000"}' `
        -ErrorAction SilentlyContinue

    if (-not $connections) {
        # Try listing workspaces first
        $workspaces = Invoke-RestMethod -Uri "$baseUrl/workspaces/list" -Method Post `
            -ContentType "application/json" -Body '{}' -ErrorAction Stop
        $wsId = $workspaces.workspaces[0].workspaceId
        Log "Found workspace: $wsId"

        $connections = Invoke-RestMethod -Uri "$baseUrl/connections/list" -Method Post `
            -ContentType "application/json" `
            -Body "{`"workspaceId`":`"$wsId`"}" -ErrorAction Stop
    }

    $enabledConnections = $connections.connections | Where-Object { $_.status -eq "active" }
    Log "Found $($enabledConnections.Count) enabled connections."

    foreach ($conn in $enabledConnections) {
        $connId = $conn.connectionId
        $connName = $conn.name
        Log "Triggering sync for: $connName ($connId)"
        try {
            Invoke-RestMethod -Uri "$baseUrl/connections/sync" -Method Post `
                -ContentType "application/json" `
                -Body "{`"connectionId`":`"$connId`"}" -ErrorAction Stop
            Log "  Sync triggered successfully."
        } catch {
            Log "  ERROR triggering sync: $_"
        }
    }
} catch {
    Log "ERROR listing connections: $_"
}

# --- 4. Wait for syncs to complete (up to 2 hours) ---
Log "Waiting for syncs to complete (checking every 5 minutes, max 2 hours)..."
$maxWait = 7200
$waited = 0
while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 300
    $waited += 300
    Log "Syncs running... ($([math]::Round($waited/60)) min elapsed)"

    # Check if any syncs are still running
    try {
        $jobs = Invoke-RestMethod -Uri "$baseUrl/jobs/list" -Method Post `
            -ContentType "application/json" `
            -Body '{"configTypes":["sync"],"pagination":{"pageSize":20,"rowOffset":0}}' `
            -ErrorAction SilentlyContinue
        $running = ($jobs.jobs | Where-Object { $_.job.status -eq "running" -or $_.job.status -eq "pending" }).Count
        if ($running -eq 0) {
            Log "All syncs completed."
            break
        }
        Log "  $running syncs still running..."
    } catch {
        Log "  Could not check job status: $_"
    }
}

# --- 5. Run Klaviyo sync (direct API, no Docker needed) ---
Log "Running Klaviyo sync..."
$klaviyoScript = "C:\Users\ReadyPlayerOne\analyticsdashboard\measurement-platform\orchestration\klaviyo_sync.py"
try {
    python $klaviyoScript 2>&1 | Tee-Object -FilePath $logFile -Append
    Log "Klaviyo sync complete."
} catch {
    Log "ERROR running Klaviyo sync: $_"
}

# --- 6. Run dbt ---
Log "Running dbt..."
$dbtDir = "C:\Users\ReadyPlayerOne\analyticsdashboard\measurement-platform\dbt"
$envFile = "C:\Users\ReadyPlayerOne\analyticsdashboard\measurement-platform\.env"

# Load env vars
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}

Push-Location $dbtDir
dbt run 2>&1 | Tee-Object -FilePath $logFile -Append
dbt test 2>&1 | Tee-Object -FilePath $logFile -Append
Pop-Location

Log "dbt run + test complete."

# --- 7. Post Chubble Gum performance report to Slack ---
Log "Generating and posting Chubble Gum report to Slack..."
$reportScript = "C:\Users\ReadyPlayerOne\analyticsdashboard\measurement-platform\orchestration\chubble_report.py"
try {
    python $reportScript 2>&1 | Tee-Object -FilePath $logFile -Append
    Log "Chubble Gum report posted to Slack."
} catch {
    Log "ERROR posting report: $_"
}

# --- 8. Done ---
Log "Sync pipeline complete. Data is fresh. Report posted."
Log "To stop Docker and reclaim RAM, run: stop-airbyte.ps1"
