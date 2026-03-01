# Prefect — full commands (copy-paste by step)

Use **three separate PowerShell windows**. Replace `YOUR-SERVICE-ROLE-KEY` with your real Supabase service_role key.

---

## Step 0 — One-time install (any window, once)

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\orchestration\prefect"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m pip install -r requirements.txt
```

---

## Window 1 — Prefect server (leave running)

Open PowerShell and run:

```powershell
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m prefect server start
```

Leave this window open. UI: **http://127.0.0.1:4200**

---

## Window 2 — Deploy + optional manual flow run

Open a **new** PowerShell. Run these in order.

### 2a — Set env and create work pool (first time only)

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"

# Create work pool (if it says "already exists", that's fine — continue to 2b)
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m prefect work-pool create default-agent-pool --type process
```

### 2b — Deploy the daily schedule

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\orchestration\prefect\deployments"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
.\deploy.ps1
```

When prompted **"Would you like your workers to pull your flow code from a remote storage location?"** type **n** and Enter.

### 2c — (Optional) Run the flow once to test

Prefect 3 no longer has `prefect flow run`. Use either:

**Option A — Run in-process (no worker needed)**  
From repo root, with env vars set:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
$env:DBT_PROJECT_DIR = "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dbt"
$env:SUPABASE_URL = "https://xopsomagbnsnadxxhzhx.supabase.co"
$env:SUPABASE_SERVICE_KEY = "YOUR-SERVICE-ROLE-KEY"
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"

C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe orchestration/prefect/flows/daily_pipeline.py
```

**Option B — Trigger deployment (worker must be running in Window 3)**  
Creates a run that the worker picks up; use `--watch` to wait for it:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"

C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m prefect deployment run daily_pipeline/daily --watch
```

---

## Window 3 — Worker (leave running)

Open **another** PowerShell. Run this block once; then leave the window open so scheduled runs execute.

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
$env:DBT_PROJECT_DIR = "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dbt"
$env:SUPABASE_URL = "https://xopsomagbnsnadxxhzhx.supabase.co"
$env:SUPABASE_SERVICE_KEY = "YOUR-SERVICE-ROLE-KEY"
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"

C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m prefect worker start --pool default-agent-pool
```

---

## Summary

| Window | Action |
|--------|--------|
| **1** | `prefect server start` — leave running |
| **2** | Work pool + `deploy.ps1` (+ optional flow run) |
| **3** | Set env vars + `prefect worker start --pool default-agent-pool` — leave running |

Replace **YOUR-SERVICE-ROLE-KEY** with your Supabase **service_role** key (Settings → API in Supabase Dashboard).
