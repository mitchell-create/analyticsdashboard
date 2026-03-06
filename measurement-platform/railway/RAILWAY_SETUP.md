# Railway + Prefect Cloud setup (measurement-platform)

Deploy:
- Metabase on Railway
- Prefect worker on Railway
- Prefect API server (choose Prefect Cloud or self-host on Railway)

You can run either:
- **Option A:** Prefect Cloud (managed)
- **Option B:** Self-hosted Prefect server on Railway (no Prefect Cloud key required)

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
4. **Prefect server service** (only for self-hosted option)

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

- `PREFECT_API_URL` (Prefect Cloud API URL OR self-hosted Prefect server URL + `/api`)
- `PREFECT_API_KEY` (required for Prefect Cloud; not required for self-hosted unless you enable auth)
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

### 2.3 Prefect server service (self-hosted option)

- Build context: `measurement-platform`
- Dockerfile: `railway/Dockerfile.prefect-server`
- Optional config file: `railway/railway.prefect-server.toml`

Set environment variables:

- `PREFECT_API_DATABASE_CONNECTION_URL` (recommended; use Railway Postgres)

Example value using Railway Postgres references:

`postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}`

Then set worker:

- `PREFECT_API_URL=https://<prefect-server-public-domain>/api`
- Remove `PREFECT_API_KEY` if not using auth.

---

## 3) Prefect API setup (choose one)

### Option A: Prefect Cloud

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

### Option B: Self-hosted Prefect server on Railway

1. Deploy the Prefect server service.
2. Generate a public domain for Prefect server in Railway networking.
3. Set worker variable:
   - `PREFECT_API_URL=https://<your-prefect-server-domain>/api`
4. No Prefect Cloud key required for this mode.

---

## 4) Deploy flow (Cloud or self-hosted)

From repo root:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
prefect deploy -n daily
```

This registers `daily_pipeline` from `prefect.yaml` against the API URL in your local shell (`PREFECT_API_URL`).

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
- For self-hosted Prefect, make sure your local shell points at the self-hosted API before running deploy commands:
  - `prefect config set PREFECT_API_URL="https://<prefect-server-domain>/api"`
