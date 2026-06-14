# setup-task-scheduler.ps1 — Register Windows Task Scheduler tasks for Airbyte sync
# Run this once as Administrator to set up the monthly sync schedule.
#
# Creates two scheduled tasks:
#   1. "Airbyte Sync - Start" — runs at 2:00 AM on the 13th and 31st of each month
#   2. "Airbyte Sync - Stop"  — runs at 6:00 AM on the 13th and 31st (4 hours later)
#
# Uses schtasks.exe with XML for monthly triggers (PowerShell's New-ScheduledTaskTrigger
# does not support -Monthly).

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$startScript = Join-Path $scriptDir "start-airbyte-sync.ps1"
$stopScript = Join-Path $scriptDir "stop-airbyte.ps1"

# Verify scripts exist
if (-not (Test-Path $startScript)) { Write-Error "start-airbyte-sync.ps1 not found at $startScript"; exit 1 }
if (-not (Test-Path $stopScript)) { Write-Error "stop-airbyte.ps1 not found at $stopScript"; exit 1 }

$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

# --- Task 1: Start sync at 2:00 AM on 13th and 31st ---
$startXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Start Docker Desktop, trigger Airbyte syncs, run dbt. Runs on 13th and 31st at 2am.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-04-13T02:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByMonth>
        <DaysOfMonth><Day>13</Day><Day>31</Day></DaysOfMonth>
        <Months><January/><February/><March/><April/><May/><June/><July/><August/><September/><October/><November/><December/></Months>
      </ScheduleByMonth>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$user</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-ExecutionPolicy Bypass -File "$startScript"</Arguments>
    </Exec>
  </Actions>
</Task>
"@

$startXmlPath = Join-Path $env:TEMP "airbyte-start-task.xml"
$startXml | Out-File -FilePath $startXmlPath -Encoding Unicode
schtasks /Create /TN "Airbyte Sync - Start" /XML $startXmlPath /F
Remove-Item $startXmlPath
Write-Host "Registered: 'Airbyte Sync - Start' (2:00 AM on 13th and 31st)"

# --- Task 2: Stop Docker at 6:00 AM on 13th and 31st ---
$stopXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Stop Docker Desktop and WSL to reclaim RAM. Runs on 13th and 31st at 6am.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-04-13T06:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByMonth>
        <DaysOfMonth><Day>13</Day><Day>31</Day></DaysOfMonth>
        <Months><January/><February/><March/><April/><May/><June/><July/><August/><September/><October/><November/><December/></Months>
      </ScheduleByMonth>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$user</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-ExecutionPolicy Bypass -File "$stopScript"</Arguments>
    </Exec>
  </Actions>
</Task>
"@

$stopXmlPath = Join-Path $env:TEMP "airbyte-stop-task.xml"
$stopXml | Out-File -FilePath $stopXmlPath -Encoding Unicode
schtasks /Create /TN "Airbyte Sync - Stop" /XML $stopXmlPath /F
Remove-Item $stopXmlPath
Write-Host "Registered: 'Airbyte Sync - Stop' (6:00 AM on 13th and 31st)"

Write-Host ""
Write-Host "Done! Tasks registered. View them in Task Scheduler."
Write-Host "  - 'Airbyte Sync - Start' runs at 2:00 AM on 13th and 31st"
Write-Host "  - 'Airbyte Sync - Stop' runs at 6:00 AM on 13th and 31st"
Write-Host "Logs: $HOME\.airbyte\sync-log-<date>.txt"
