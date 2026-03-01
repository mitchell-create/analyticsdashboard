# Prefect setup — daily pipeline (Windows)

Run the daily pipeline (dbt run + dbt test) on a schedule after Airbyte syncs. Use a local Prefect server or Prefect Cloud.

---

## 1. Prerequisites

- **Python 3.10+** (same as dbt).
- **dbt** installed and working (you already ran `dbt run` from the `dbt` folder).
- **pipeline_runs** table in Supabase (from `warehouse/schema/050_quality.sql`). If you haven’t applied that migration, run it in Supabase SQL Editor or apply the schema.

---

## 2. Install Prefect and dependencies

**Option A — Install in current environment (simplest)**

From the repo root or `orchestration/prefect`:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\orchestration\prefect"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m pip install -r requirements.txt
```

You may see dependency conflicts (e.g. gotrue/openai/supafunc wanting older httpx/anyio). The install still succeeds; try running the flow. If you get import or runtime errors, use Option B.

**Option B — Use a virtual environment (avoids conflicts with other packages)**

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\orchestration\prefect"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Then run Prefect commands using the venv’s Python (e.g. `python -m prefect ...` or ensure the venv is activated when you run the worker).

---

## 3. Environment variables

Set these so the flow can find dbt, Supabase, and (optionally) Slack:

**Required for dbt + recording runs:**

- **DBT_PROJECT_DIR** — Path to the dbt project. If you don’t set it, the flow uses the repo’s `dbt` folder automatically.
- **SUPABASE_URL** — Your Supabase project URL (e.g. `https://xopsomagbnsnadxxhzhx.supabase.co`).
- **SUPABASE_SERVICE_KEY** — Service role key from Supabase (Settings → API → service_role).

**Optional:**

- **AIRBYTE_API_KEY** + **AIRBYTE_WORKSPACE_ID** — To check Airbyte sync before running dbt (currently a no-op if unset).
- **SLACK_BOT_TOKEN** + **SLACK_ALERT_CHANNEL_ID** — To post alerts on failure.

Example (PowerShell, this session only):

```powershell
$env:DBT_PROJECT_DIR = "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dbt"
$env:SUPABASE_URL = "https://xopsomagbnsnadxxhzhx.supabase.co"
$env:SUPABASE_SERVICE_KEY = "your-service-role-key"
# Optional: $env:SLACK_BOT_TOKEN = "xoxb-..."; $env:SLACK_ALERT_CHANNEL_ID = "C..."
```

**Important:** When you start the Prefect worker (step 6), start it from a terminal where **dbt is on PATH** (e.g. the same PowerShell where you run `dbt run`). If you normally add Python Scripts to PATH, do that before starting the worker:

```powershell
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"
```

---

## 4. Start the Prefect server (local)

In a **separate** PowerShell window, start the Prefect server so you can run and schedule flows:

```powershell
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m prefect server start
```

Leave this running. The UI is at **http://127.0.0.1:4200**. You can open it in a browser to see runs and deployments.

---

## 5. Run the daily pipeline once (manual test)

From the repo root (so Prefect can find the flow file), with env vars and dbt on PATH set:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
# Set DBT_PROJECT_DIR, SUPABASE_URL, SUPABASE_SERVICE_KEY if you didn’t already
# Prefect 3: run flow in-process (no worker needed)
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe orchestration/prefect/flows/daily_pipeline.py
```

You should see the flow run: check Airbyte (or skip), run dbt, run dbt test, then record success in `pipeline_runs`. Check the Prefect UI at http://127.0.0.1:4200 and Supabase `pipeline_runs` table.

---

## 6. Deploy and schedule (daily run)

**Option A — PowerShell script (recommended on Windows)**

From the repo root:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\orchestration\prefect\deployments"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
.\deploy.ps1
```

Then start a worker so scheduled runs actually execute. In a **new** PowerShell (with dbt on PATH and env vars set):

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
# Set DBT_PROJECT_DIR, SUPABASE_URL, SUPABASE_SERVICE_KEY
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m prefect worker start --pool default-pool
```

Leave the worker running. The deployment is scheduled (e.g. daily at 6 AM Eastern); adjust the cron in `deploy.ps1` if you want a different time (e.g. after your Airbyte sync).

**Option B — Manual deploy (no script)**

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"

# Build deployment (daily at 6 AM Eastern; change cron as needed)
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m prefect deployment build "orchestration/prefect/flows/daily_pipeline.py:daily_pipeline" --name "daily" --cron "0 6 * * *" --output "orchestration/prefect/deployments/daily_pipeline-deployment.yaml"

# Apply
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m prefect deployment apply "orchestration/prefect/deployments/daily_pipeline-deployment.yaml"
```

Then start the worker as in Option A.

---

## 7. Checklist

- [ ] Prefect + deps installed (`pip install -r requirements.txt`).
- [ ] `pipeline_runs` table exists in Supabase (from `050_quality.sql`).
- [ ] Env vars set: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`; optionally `DBT_PROJECT_DIR`, Slack, Airbyte.
- [ ] Prefect server running (`prefect server start`); UI at http://127.0.0.1:4200.
- [ ] Manual flow run succeeded (`python orchestration/prefect/flows/daily_pipeline.py` or `prefect deployment run daily_pipeline/daily --watch`).
- [ ] Deployment created and applied (`deploy.ps1` or manual deploy).
- [ ] Worker running (`prefect worker start --pool default-pool`) in a terminal where dbt is on PATH.

---

## Changing the schedule

The default cron is `0 6 * * *` (6:00 AM Eastern daily). To run after your Airbyte sync (e.g. 5 AM Eastern for Airbyte, 6 AM Eastern for Prefect):

- Edit `deployments/deploy.ps1` and change the `--cron` to `0 7 * * *`, then run `deploy.ps1` again and re-apply the deployment.
- Or build/apply the deployment manually with the desired `--cron` value.
