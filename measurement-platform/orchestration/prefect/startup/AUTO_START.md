# Run Prefect server and worker automatically (Windows)

Use **Task Scheduler** so the Prefect server and worker start when you log on. No need to keep PowerShell windows open.

---

## 1. Create the “Prefect Server” task

1. Open **Task Scheduler** (search “Task Scheduler” in Start).
2. Click **Create Task** (not “Create Basic Task”).
3. **General** tab:
   - Name: `Prefect Server`
   - Option: **Run only when user is logged on** (or “Run whether user is logged on or not” if you want it to run before logon; then use a service account or SYSTEM).
   - Check **Run with highest privileges** only if needed.
4. **Triggers** tab:
   - **New…** → Begin the task: **At log on** → choose your user → **OK**.
5. **Actions** tab:
   - **New…** → Action: **Start a program**.
   - Program/script: `powershell.exe`
   - Add arguments: `-NoProfile -ExecutionPolicy Bypass -File "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\orchestration\prefect\startup\start_prefect_server.ps1"`
   - Start in: `C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform`
   - **OK**.
6. **Conditions** tab (optional): Uncheck **Start the task only if the computer is on AC power** if you use a laptop on battery.
7. **Settings** tab: Leave default; optionally check **Allow task to be run on demand**.
8. **OK** to save.

---

## 2. Create the “Prefect Worker” task

1. **Create Task** again.
2. **General**: Name: `Prefect Worker`. Same “Run only when user is logged on” (or your choice).
3. **Triggers**: **At log on** (same as above).
4. **Actions**:
   - Program: `powershell.exe`
   - Add arguments: `-NoProfile -ExecutionPolicy Bypass -File "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\orchestration\prefect\startup\start_prefect_worker.ps1"`
   - Start in: `C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform`
5. **Conditions**: Same as server (e.g. uncheck AC power if needed).
6. **Settings**: Optional: **If the task fails, restart every**: 1 minute, **Attempt to restart up to**: 3 times (so the worker restarts if it crashes).
7. **OK** to save.

**Optional:** Add a **Delay task for** (e.g. 15 seconds) on the Worker task’s trigger so the server starts first.

---

## 3. Run the tasks

- In Task Scheduler, select **Prefect Server** → **Run**.
- Select **Prefect Worker** → **Run**.
- Or log off and log back on; both should start at logon.

---

## 4. Check that they’re running

- Open **http://127.0.0.1:4200** — Prefect UI should load.
- In the UI, confirm the worker appears (e.g. under Workers / work pool `default-agent-pool`).
- Trigger a run: `prefect deployment run daily_pipeline/daily --watch` (from any PowerShell with `PREFECT_API_URL` set).

---

## 5. Stop them

- In Task Scheduler: **Prefect Server** → **End** (if you enabled “Run on demand”, the task may show as running).
- Or in a PowerShell run: `Get-Process -Name python | Where-Object { $_.CommandLine -like '*prefect*' } | Stop-Process` (use with care; this stops Prefect Python processes).

---

## Notes

- **Supabase key:** The worker script has `SUPABASE_SERVICE_KEY` in it. If you change the key, edit `start_prefect_worker.ps1`.
- **No windows:** The tasks run in the background; no PowerShell windows will stay open.
- **First logon:** If the worker starts before the server, wait a few seconds and run the Worker task again from Task Scheduler, or add a delay (step 2 optional) so the server starts first.
