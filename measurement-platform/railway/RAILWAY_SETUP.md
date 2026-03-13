# Railway Setup — Metabase + Prefect Worker

Deploy Metabase and your Prefect worker to Railway. Use **Prefect Cloud** (free) for the API/UI, and run the worker on Railway so flows execute in the cloud.

---

## Prerequisites

1. **Railway account** (Hobby plan)
2. **Prefect Cloud account** — Sign up at [prefect.cloud](https://prefect.cloud), create a workspace, generate an API key
3. **GitHub** — Push this repo so Railway can deploy from it

---

## Step 1: Install Railway CLI

```powershell
npm install -g @railway/cli
```

Or: `winget install Railway.Railway` (if available), or download from [Railway CLI releases](https://github.com/railwayapp/cli/releases)

---

## Step 2: Log in and create project

```powershell
railway login
```

A browser window will open — complete the login.

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
railway init
```

Choose **Create a new project** and name it `measurement-platform`.

---

## Step 3: Add Postgres (for Metabase)

1. In [Railway Dashboard](https://railway.app/dashboard) → your project
2. Click **+ New** → **Database** → **Add PostgreSQL**
3. Copy the `DATABASE_URL` or individual vars (`PGHOST`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`, `PGPORT`) — you'll need them for Metabase

---

## Step 4: Deploy Metabase

1. **+ New** → **GitHub Repo** (or **Empty Service** if deploying from CLI)
2. If GitHub: Select this repo, choose `measurement-platform` as root directory
3. **Settings** → **Build**:
   - Builder: **Dockerfile**
   - Dockerfile path: `railway/Dockerfile.metabase`
4. **Settings** → **Variables** — add:

   | Variable | Value |
   |----------|-------|
   | `MB_DB_TYPE` | `postgres` |
   | `MB_DB_HOST` | Postgres host from Step 3 |
   | `MB_DB_PORT` | `5432` |
   | `MB_DB_DBNAME` | Postgres database name |
   | `MB_DB_USER` | Postgres user |
   | `MB_DB_PASS` | Postgres password |

   Or set `DATABASE_URL` and Metabase can parse it — check [Metabase env docs](https://www.metabase.com/docs/latest/installation-and-operation/configuring-metabase#database-connection-environment-variables).

5. **Deploy** — Metabase will start. Open the generated URL, complete setup wizard, then add **Supabase** as a data source (use your `SUPABASE_DB_URL` or host/user/pass).

---

## Step 5: Deploy Prefect worker

1. **+ New** → **GitHub Repo** (or **Empty Service**)
2. Root: `measurement-platform`
3. **Settings** → **Build**:
   - Builder: **Dockerfile**
   - Dockerfile path: `railway/Dockerfile.worker`
4. **Settings** → **Variables** — add:

   | Variable | Value |
   |----------|-------|
   | `PREFECT_API_URL` | From Prefect Cloud: `https://api.prefect.cloud/api/accounts/<account_id>/workspaces/<workspace_id>` |
   | `PREFECT_API_KEY` | Your Prefect Cloud API key |
   | `SUPABASE_URL` | Your Supabase URL |
   | `SUPABASE_SERVICE_KEY` | Supabase service key |
   | `SUPABASE_DB_HOST` | e.g. `aws-1-us-east-2.pooler.supabase.com` |
   | `SUPABASE_DB_USER` | e.g. `postgres.xopsomagbnsnadxxhzhx` |
   | `SUPABASE_DB_PASSWORD` | Supabase DB password |
   | `DBT_PROJECT_DIR` | `/app/dbt` |
   | `CLIENT_SLUG` | e.g. `expand` or your client slug |
   | `SLACK_BOT_TOKEN` | (optional) For failure alerts |
   | `SLACK_ALERT_CHANNEL_ID` | (optional) Channel ID for alerts |

5. **Deploy**

---

## Step 6: Connect Prefect to Prefect Cloud and deploy flows

On your **local machine** (one-time):

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"

# Point Prefect to Cloud instead of local server
$env:PREFECT_API_URL = "https://api.prefect.cloud/api/accounts/YOUR_ACCOUNT_ID/workspaces/YOUR_WORKSPACE_ID"
$env:PREFECT_API_KEY = "your-prefect-cloud-api-key"

# Deploy the daily_pipeline flow (creates deployment in Prefect Cloud)
# Ensure work pool "default-agent-pool" exists in Prefect Cloud
prefect work-pool create default-agent-pool --type process 2>$null
prefect deploy -n daily
```

The Railway worker (pool `default-agent-pool`) will pick up jobs from Prefect Cloud and run them.

---

## Step 7: Ensure work pool exists in Prefect Cloud

In Prefect Cloud UI → Work Pools → create `default-agent-pool` (type: Process) if it doesn't exist. The worker connects to this pool.

---

## Costs

- **Railway Hobby**: ~$5 credit/month. Metabase + worker may use most of it.
- **Prefect Cloud**: Free tier (20k task runs/month).
- **Supabase**: Your existing plan.

---

## Troubleshooting

- **Worker not picking up jobs**: Check worker logs in Railway. Ensure `PREFECT_API_URL` and `PREFECT_API_KEY` match Prefect Cloud.
- **dbt fails in flow**: Check `SUPABASE_DB_*` env vars. Worker needs network access to Supabase (Railway egress is allowed).
- **Metabase won't start**: Verify `MB_DB_*` point to the Railway Postgres instance.
