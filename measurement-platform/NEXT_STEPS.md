# Next steps — detailed and simple

Use this after you have **Airbyte**, **dbt**, and **Metabase** working (Executive Overview + Channel Performance). Steps are in order; do one, then the next.

---

## Step 1: Finish Prefect (daily dbt run)

Prefect runs `dbt run` and `dbt test` on a schedule so your marts stay up to date after Airbyte syncs.

### 1.1 Set environment variables

Open PowerShell and set these (replace with your real values). Do this in the same session where you will run Prefect, or add them to your user environment.

```powershell
$env:DBT_PROJECT_DIR = "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dbt"
$env:SUPABASE_URL = "https://xopsomagbnsnadxxhzhx.supabase.co"
$env:SUPABASE_SERVICE_KEY = "your-service-role-key"
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"
```

- **SUPABASE_SERVICE_KEY:** In Supabase Dashboard → **Settings** → **API** → copy the **service_role** key (secret). Do not use the anon key.

### 1.2 Make sure `pipeline_runs` exists in Supabase

The flow writes run history to the `pipeline_runs` table. If you already applied all schema files (000–050), you have it. If not:

1. Open Supabase Dashboard → **SQL Editor**.
2. Open the file **`warehouse/schema/050_quality.sql`** in your project and run the `CREATE TABLE IF NOT EXISTS public.pipeline_runs ...` part (or run the whole file).

### 1.3 Start the Prefect server

In a **new** PowerShell window, run:

```powershell
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m prefect server start
```

Leave this window open. Open **http://127.0.0.1:4200** in your browser to see the Prefect UI.

### 1.4 Run the daily pipeline once (test)

In **another** PowerShell (with the env vars from 1.1 set), run:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
# Prefect 3: run in-process (no prefect flow run)
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe orchestration/prefect/flows/daily_pipeline.py
```

- If it finishes without errors, check the Prefect UI (http://127.0.0.1:4200) and the **`pipeline_runs`** table in Supabase. You should see a new row with status **success**.
- If you get an error (e.g. “dbt not found”), make sure **dbt** is on PATH (you added Scripts in 1.1) and you’re in the repo folder.

### 1.4 Create work pool (Prefect 3, one-time)

From repo root with Prefect server running: `prefect work-pool create default-agent-pool --type process`. (If it says already exists, skip.)

### 1.5 Deploy the daily schedule

In the same PowerShell (env vars + PATH set):

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\orchestration\prefect\deployments"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
.\deploy.ps1
```

You should see “Deployed: daily_pipeline (daily at 6:00 AM Eastern). If deploy.ps1 fails, create the work pool first (step 1.4), then run deploy.ps1 again”.

### 1.6 Start the worker (so scheduled runs actually run)

In **another** PowerShell (env vars + PATH set again):

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
$env:DBT_PROJECT_DIR = "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dbt"
$env:SUPABASE_URL = "https://xopsomagbnsnadxxhzhx.supabase.co"
$env:SUPABASE_SERVICE_KEY = "your-service-role-key"
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m prefect worker start --pool default-agent-pool
```

Leave this window open. Every day at 6:00 AM Eastern the flow will run: dbt run, dbt test, and a row in `pipeline_runs`.

**Summary Step 1:** Set env vars → ensure `pipeline_runs` exists → start Prefect server → create work pool (1.4) → run deploy.ps1 → run flow once (test) → start worker. After that, the daily pipeline is automated.

---

## Step 2: Optional — Add date filters in Metabase

So all charts on a dashboard use the same date range:

1. Open a dashboard in Metabase (e.g. Executive Overview).
2. Click the **pencil** to edit.
3. Click **Add a filter** → **Time** → **Date filter** (or **Single date**).
4. Connect the filter to the questions that use dates (e.g. **report_date**).
5. Save the dashboard.

Repeat for Channel Performance if you want.

---

## Step 3: Optional — TikTok organic (Metricool)

Only if you use **TikTok organic** and want views/likes/followers by day:

1. Connect your TikTok account in **Metricool** and set up export or API sync into Supabase (see **`ops/client-provision/INGESTION.md`**).
2. Load data into a raw table (e.g. `raw.metricool_tiktok_daily`) with columns like **report_date**, **views**, **likes**, **followers**.
3. Point dbt **sources** and **`stg_metricool_tiktok`** at that table, then run **`fact_tiktok_organic_daily`**.
4. In Metabase, add the **Organic TikTok + Email** dashboard from **`dashboards/metabase/MVP_dashboard_spec.md`** (charts from `fact_tiktok_organic_daily`).

---

## Step 4: Optional — Klaviyo sent/opens/clicks

Right now **fact_klaviyo_daily** has only campaign metadata; sent/opens/clicks are 0. To get real numbers:

1. In Airbyte, add or enable a Klaviyo stream that has **sends**, **opens**, **clicks** (e.g. campaign metrics or flow metrics).
2. Update **`stg_klaviyo_campaigns`** (or add a new staging model) to read from that stream and map those columns.
3. Run **`dbt run --select stg_klaviyo_campaigns fact_klaviyo_daily`**.

---

## Step 5: Optional — Experiments (GeoLift / CausalImpact)

When you want to run **lift tests** and show results in Metabase:

1. Use **`services/model-runner/`**: run GeoLift or CausalImpact and write results into **`experiments`** and **`experiment_results`** (see the runner README or code).
2. In Metabase, add the **Experiment Results** dashboard from **`dashboards/metabase/MVP_dashboard_spec.md`** (tables/charts from **`experiments`** and **`experiment_results`**).

---

## Step 6: Optional — Slack bot (alerts + Q&A)

When you want **Slack alerts** on pipeline failure or **natural-language → SQL** in Slack:

1. Create a Slack app, get **Bot Token** and **Signing Secret**, create a channel for alerts.
2. Copy **`.env.example`** to **`.env`** and set **SLACK_BOT_TOKEN**, **SLACK_SIGNING_SECRET**, **SLACK_ALERT_CHANNEL_ID**, plus **SUPABASE_*** for the bot.
3. In **`services/slack-bot/`**: run **`npm install`**, **`npm run build`**, **`npm start`** (or run via your process manager).
4. In **Prefect**, set **SLACK_BOT_TOKEN** and **SLACK_ALERT_CHANNEL_ID** so the daily pipeline can post failure alerts to Slack.

---

## Step 7: Optional — Fix dbt warning

If you see: **“Configuration paths exist … seeds.measurement_platform.dim_geo”**:

- Open **`dbt/dbt_project.yml`** and either remove the **seeds.measurement_platform.dim_geo** block if you don’t need it, or align it with how the **dim_geo** seed is defined (name and path). Then run **`dbt run`** again; the warning should go away.

---

## Quick reference

| Goal | What to do |
|------|------------|
| **Daily dbt after Airbyte** | Complete Step 1 (Prefect). |
| **Filter dashboards by date** | Step 2 (Metabase date filter). |
| **TikTok organic in Metabase** | Step 3 (Metricool + dbt + dashboard). |
| **Klaviyo sent/opens/clicks** | Step 4 (Airbyte stream + dbt). |
| **Lift test results in Metabase** | Step 5 (model runner + dashboard). |
| **Slack alerts / Q&A** | Step 6 (Slack app + env + run bot). |
| **No dbt warning** | Step 7 (dbt_project.yml). |

Do **Step 1** first so the pipeline runs every day; the rest are optional and in any order.
