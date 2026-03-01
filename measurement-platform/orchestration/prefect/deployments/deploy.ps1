# deploy.ps1 — Deploy Prefect 3 flows (Windows).
# Prerequisites: prefect installed, Prefect server running, PREFECT_API_URL set.
# Run from repo root. Creates work pool if needed, then deploys daily_pipeline.

$ErrorActionPreference = "Stop"
$RepoRoot = "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
if (-not $env:PREFECT_API_URL) { $env:PREFECT_API_URL = "http://127.0.0.1:4200/api" }

# Set env vars so prefect.yaml job_variables get the values (for pipeline_runs Supabase writes)
# IMPORTANT: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in your environment or .env — do not hardcode here
$env:DBT_PROJECT_DIR = "$RepoRoot\dbt"
if (-not $env:SUPABASE_URL) { $env:SUPABASE_URL = "YOUR_SUPABASE_URL" }
if (-not $env:SUPABASE_SERVICE_KEY) { $env:SUPABASE_SERVICE_KEY = "YOUR_SUPABASE_SERVICE_KEY" }
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"
# Optional: Slack failure alerts (see orchestration/prefect/SLACK_ALERTS_SETUP.md)
# $env:SLACK_BOT_TOKEN = "YOUR_SLACK_BOT_TOKEN"
# $env:SLACK_ALERT_CHANNEL_ID = "YOUR_SLACK_CHANNEL_ID"

Write-Host "==> Prefect 3 deploy (repo: $RepoRoot)"
Set-Location $RepoRoot

# Ensure work pool exists (Prefect 3 uses work pools; type 'process' runs flows locally)
$poolName = "default-agent-pool"
& prefect work-pool ls 2>$null | Out-Null
$poolExists = $LASTEXITCODE -eq 0
# Create pool if it doesn't exist; --overwrite updates it if it already exists
& prefect work-pool create $poolName --type process --overwrite 2>$null

# Deploy from prefect.yaml (includes job_variables with SUPABASE_* for pipeline_runs)
# When prompted "Would you like your workers to pull your flow code from a remote storage location?" answer n (no)
& prefect deploy -n daily

if ($LASTEXITCODE -ne 0) {
  Write-Host "    Deploy failed. Ensure prefect.yaml exists and env vars SUPABASE_URL, SUPABASE_SERVICE_KEY, DBT_PROJECT_DIR are set."
  exit 1
}
Write-Host "    Deployed: daily_pipeline (daily at 6:00 AM Eastern)"
Write-Host ""
Write-Host "==> To run manually: prefect deployment run daily_pipeline/daily"
Write-Host ""
Write-Host "==> Start a worker so scheduled runs execute:"
Write-Host "    cd `"$RepoRoot`""
Write-Host "    `$env:PREFECT_API_URL = `"http://127.0.0.1:4200/api`""
Write-Host "    `$env:Path += `";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts`""
Write-Host "    prefect worker start --pool $poolName"
Write-Host "    (Set DBT_PROJECT_DIR, SUPABASE_URL, SUPABASE_SERVICE_KEY before starting worker.)"
