# Railway + Prefect Cloud setup (measurement-platform)

Deploy:
- Metabase on Railway
- Prefect worker on Railway
- Prefect Cloud for orchestration and scheduling

This setup avoids self-hosting Prefect server.

---

## 1) Prerequisites

- Railway account and CLI login
- Prefect Cloud account + API key
- GitHub repo connected to Railway
- Supabase credentials for the target client

Windows PowerShell:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
```

---

## 2) Railway services

Create one Railway project with:

1. **Postgres add-on** (Metabase app database, not your analytics warehouse)
2. **Metabase service**
3. **Prefect worker service**

### 2.1 Metabase service

- Build context: `measurement-platform`
- Dockerfile: `railway/Dockerfile.metabase`
- Optional config file: `railway/railway.metabase.toml`

Set environment variables in Railway for Metabase:

- `MB_DB_TYPE=postgres`
- `MB_DB_HOST` from Railway Postgres
- `MB_DB_PORT` from Railway Postgres
- `MB_DB_DBNAME` from Railway Postgres
- `MB_DB_USER` from Railway Postgres
- `MB_DB_PASS` from Railway Postgres

### 2.2 Prefect worker service

- Build context: `measurement-platform`
- Dockerfile: `railway/Dockerfile.worker`
- Optional config file: `railway/railway.worker.toml`

Set environment variables in Railway for worker:

- `PREFECT_API_URL` (Prefect Cloud API URL for your workspace)
- `PREFECT_API_KEY` (Prefect Cloud API key)
- `PREFECT_WORK_POOL=default-agent-pool`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_DB_HOST`
- `SUPABASE_DB_USER`
- `SUPABASE_DB_PASSWORD`
- `SUPABASE_DB_PORT=5432` (or your value)
- `DBT_PROJECT_DIR=/app/dbt`
- `DBT_PROFILES_DIR=/app/dbt`
- `CLIENT_SLUG=expand`
- Optional: `SLACK_BOT_TOKEN`, `SLACK_ALERT_CHANNEL_ID`

---

## 3) Prefect Cloud one-time setup

1. In Prefect Cloud, create a workspace and API key.
2. Copy your API URL in this format:
   - `https://api.prefect.cloud/api/accounts/<account_id>/workspaces/<workspace_id>`
3. Configure local shell:

```powershell
$env:PREFECT_API_URL = "https://api.prefect.cloud/api/accounts/<account_id>/workspaces/<workspace_id>"
$env:PREFECT_API_KEY = "<your-prefect-cloud-api-key>"
prefect cloud login --key $env:PREFECT_API_KEY --workspace "<account>/<workspace>"
```

4. Create work pool (once):

```powershell
prefect work-pool create default-agent-pool --type process
```

If it already exists, continue.

---

## 4) Deploy flow to Prefect Cloud

From repo root:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
prefect deploy -n daily
```

This registers `daily_pipeline` from `prefect.yaml`.

The deployment picks up these env vars at run-time:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_DB_HOST`
- `SUPABASE_DB_USER`
- `SUPABASE_DB_PASSWORD`
- `SUPABASE_DB_PORT`
- `DBT_PROJECT_DIR`
- `DBT_PROFILES_DIR`
- `CLIENT_SLUG`
- Slack vars (optional)

---

## 5) Validate end-to-end

1. Confirm Railway worker logs show:
   - `Starting Prefect worker in pool: default-agent-pool`
2. In Prefect Cloud, run deployment manually:
   - `daily_pipeline / daily`
3. Verify run succeeds and writes to `pipeline_runs` in Supabase.
4. Verify dbt output tables update for target client.

---

## 6) Notes

- `daily_pipeline.py` now supports client-scoped dbt runs through:
  - `CLIENT_SLUG` → `dbt run --vars "{client_slug: <slug>}"`
- `DBT_PROFILES_DIR=/app/dbt` is required so dbt can use `/app/dbt/profiles.yml`.
- Worker startup script auto-copies `dbt/profiles.yml.template` to `dbt/profiles.yml` if missing.
