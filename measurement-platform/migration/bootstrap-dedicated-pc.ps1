# bootstrap-dedicated-pc.ps1
# One-shot installer for the dedicated always-on PC that will host the warehouse + platform.
# Run from an ELEVATED PowerShell prompt: Right-click PowerShell -> Run as Administrator
# Idempotent — safe to re-run if any step fails.

#Requires -RunAsAdministrator

$ErrorActionPreference = "Continue"
$logFile = "$HOME\bootstrap-$(Get-Date -Format 'yyyy-MM-dd-HHmm').log"

function Log($msg) {
    $line = "$(Get-Date -Format 'HH:mm:ss')  $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

function Install-WingetPackage($id, $name) {
    Log "Installing $name ($id)..."
    $existing = winget list --id $id --exact 2>&1 | Select-String $id
    if ($existing) {
        Log "  Already installed — skipping."
        return
    }
    winget install --id $id --exact --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Log "  OK" } else { Log "  FAILED (exit $LASTEXITCODE) — install manually" }
}

Log "=== bootstrap-dedicated-pc.ps1 starting ==="
Log "Logging to $logFile"

# --- Core tooling ---
Install-WingetPackage "Git.Git" "Git"
Install-WingetPackage "GitHub.cli" "GitHub CLI"
Install-WingetPackage "Python.Python.3.12" "Python 3.12"
Install-WingetPackage "OpenJS.NodeJS.LTS" "Node.js 20 LTS"
Install-WingetPackage "GoLang.Go" "Go"
Install-WingetPackage "Microsoft.VisualStudioCode" "VS Code"

# --- Database ---
Install-WingetPackage "PostgreSQL.PostgreSQL.17" "PostgreSQL 17"

# --- Containers + Airbyte ---
Install-WingetPackage "Docker.DockerDesktop" "Docker Desktop"

# --- Networking + Backups ---
Install-WingetPackage "Tailscale.Tailscale" "Tailscale"
Install-WingetPackage "Rclone.Rclone" "rclone"

# --- Java (for Metabase) ---
Install-WingetPackage "EclipseAdoptium.Temurin.21.JRE" "Temurin 21 JRE"

# --- R (kept for future GeoLift re-enable; small footprint) ---
Install-WingetPackage "RProject.R" "R"

# --- Refresh PATH for current session so subsequent steps see the new binaries ---
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

# --- pip packages ---
Log "Installing Python packages..."
python -m pip install --upgrade pip 2>&1 | Out-Null
python -m pip install dbt-postgres prefect psycopg2-binary slack-sdk requests 2>&1 | Tee-Object -Append $logFile

# --- Manual download: abctl (Airbyte CLI) ---
# v0.31.0 release URL was unavailable during real-world bootstrap (Windows zip 404'd);
# v0.30.4 is the last known good Windows build.
$abctlVersion = "v0.30.4"
$abctlDir = "$HOME\abctl-$abctlVersion-windows-amd64"
if (-not (Test-Path "$abctlDir\abctl.exe")) {
    Log "Downloading abctl $abctlVersion..."
    $url = "https://github.com/airbytehq/abctl/releases/download/$abctlVersion/abctl-$abctlVersion-windows-amd64.zip"
    $zip = "$HOME\abctl.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath "$HOME" -Force
    Remove-Item $zip
    Log "  abctl extracted to $abctlDir"
} else {
    Log "abctl already present at $abctlDir"
}

# --- Manual download: Metabase JAR ---
# v0.51.x is too old to load H2 metadata files written by v0.58 — pin to a current 0.58.x.
$metabaseVersion = "v0.58.13"
$metabaseDir = "$HOME\metabase"
if (-not (Test-Path "$metabaseDir\metabase.jar")) {
    Log "Downloading Metabase JAR ($metabaseVersion)..."
    New-Item -ItemType Directory -Path $metabaseDir -Force | Out-Null
    Invoke-WebRequest -Uri "https://downloads.metabase.com/$metabaseVersion/metabase.jar" -OutFile "$metabaseDir\metabase.jar"
    Log "  Metabase JAR at $metabaseDir\metabase.jar"
}

# --- Create directory structure ---
New-Item -ItemType Directory -Path "$HOME\repos" -Force | Out-Null
New-Item -ItemType Directory -Path "$HOME\backups" -Force | Out-Null
New-Item -ItemType Directory -Path "$HOME\.airbyte" -Force | Out-Null

Log "=== bootstrap complete ==="
Log ""
Log "NEXT STEPS (manual — see MIGRATION_RUNBOOK.md):"
Log "  1. Sign in to Tailscale on this PC and the work PC"
Log "  2. git clone the repo into $HOME\repos\analyticsdashboard"
Log "  3. Initialize Postgres: set superuser password, create 'analytics' database"
Log "  4. Restart this shell so PATH updates take effect"
Log "  5. Follow MIGRATION_RUNBOOK.md to migrate data from Supabase"
