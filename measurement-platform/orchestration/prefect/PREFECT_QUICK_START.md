# Prefect pipeline — step-by-step setup

This guide walks you through setting up the daily pipeline so **dbt runs automatically after Airbyte** syncs your data.

---

## What the pipeline does

1. **Checks** that Airbyte sync completed (optional; skips if not configured)
2. **Runs** `dbt run` (rebuilds staging views and marts)
3. **Runs** `dbt test` (checks data quality)
4. **Records** the result in Supabase (`pipeline_runs` table)
5. **Sends** a Slack alert if something fails (optional; see Step 11 below)

**Important:** Airbyte runs on its own schedule. This pipeline runs **after** Airbyte. Set Airbyte to sync earlier (e.g. 5 AM) and this pipeline to run at 6 AM.

---

## Step 1: Create the pipeline_runs table in Supabase

The pipeline needs a table to record run history.

1. Open your browser and go to [supabase.com/dashboard](https://supabase.com/dashboard). Open your **analytics-dashboard** project.
2. Click **SQL Editor** in the left sidebar.
3. Click **New query**.
4. Copy and paste this SQL (from `warehouse/schema/050_quality.sql`):

```sql
CREATE TABLE IF NOT EXISTS public.pipeline_runs (
  id            BIGSERIAL PRIMARY KEY,
  run_date      DATE NOT NULL,
  flow_name     TEXT NOT NULL,
  status        TEXT NOT NULL,
  started_at   TIMESTAMPTZ NOT NULL,
  finished_at   TIMESTAMPTZ,
  message       TEXT,
  metadata      JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_date ON public.pipeline_runs (run_date);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_flow ON public.pipeline_runs (flow_name);
```

5. Click **Run** (or press Ctrl+Enter).
6. You should see "Success. No rows returned." That means the table was created.

---

## Step 2: Install Prefect and dependencies

1. Open **PowerShell**.
2. Run these commands one at a time:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\orchestration\prefect"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m pip install -r requirements.txt
```

3. Wait for the install to finish. If you see dependency warnings, that’s usually fine.

---

## Step 3: Get your Supabase service role key

The pipeline needs this to write to `pipeline_runs`.

1. In Supabase dashboard, click **Settings** (gear icon) in the left sidebar.
2. Click **API**.
3. Under **Project API keys**, find **service_role** (the secret one, not anon).
4. Click **Reveal** and copy the key. Save it somewhere safe — you’ll use it in Step 5.

---

## Step 4: Update the worker script with your keys

1. Open this file in Cursor or Notepad:

   `C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\orchestration\prefect\startup\start_prefect_worker.ps1`

2. Find the line that says `$env:SUPABASE_SERVICE_KEY = "..."`.
3. Replace the value inside the quotes with your **actual** service role key from Step 3.
4. Save the file.

5. Check **SUPABASE_URL** in the same file. It should be:

   `https://xopsomagbnsnadxxhzhx.supabase.co`

   If your project has a different URL, update it.

---

## Step 5: Start the Prefect server (first terminal)

1. Open **PowerShell**.
2. Run:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m prefect server start
```

3. Leave this window open. You should see something like "Prefect server started."
4. Open **http://127.0.0.1:4200** in your browser. You should see the Prefect UI.

---

## Step 6: Deploy the daily pipeline

1. Open a **second** PowerShell window (keep the server running in the first).
2. Run these commands one at a time:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"
.\orchestration\prefect\deployments\deploy.ps1
```

3. If it asks "Would you like your workers to pull your flow code from a remote storage location?" type **n** and press Enter.
4. You should see "Deployed: daily_pipeline (daily at 6:00 AM Eastern)".

---

## Step 7: Start the Prefect worker (second terminal)

The worker is what actually runs the pipeline when it’s scheduled (or when you trigger it manually).

1. In the same second PowerShell (or a new one), run:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
.\orchestration\prefect\startup\start_prefect_worker.ps1
```

2. Leave this window open. You should see "Worker started" or similar. The worker is now waiting for jobs.

---

## Step 8: Run the pipeline once (test)

1. Open a **third** PowerShell window.
2. Run:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe orchestration/prefect/flows/daily_pipeline.py
```

3. Watch the output. You should see it run dbt run, then dbt test, then finish.
4. In Supabase, open **Table Editor** → **pipeline_runs**. You should see a new row with `status: success`.

---

## Step 9: Schedule Airbyte before Prefect

The pipeline runs **dbt after Airbyte**. So Airbyte must run first.

1. In **Airbyte**, open each connection (Meta, Google, TikTok, Shopify, Klaviyo).
2. Set the sync schedule to **daily** (e.g. 5:00 AM Eastern or your preferred time).
3. Prefect is set to run at **6:00 AM Eastern**. So:
   - 5:00 AM Eastern — Airbyte syncs
   - 6:00 AM Eastern — Prefect runs dbt

If you want a different time, edit `deploy.ps1` and change the `--cron` value, then run `deploy.ps1` again.

---

## Step 10: (Optional) Auto-start on logon

To avoid starting the server and worker manually every time:

1. Open **Task Scheduler** (search in Start menu).
2. Follow the instructions in `orchestration/prefect/startup/AUTO_START.md` to create two tasks:
   - **Prefect Server** — runs at logon
   - **Prefect Worker** — runs at logon (with a delay so the server starts first)

After that, the server and worker start when you log in to Windows.

---

## Step 11: (Optional) Slack failure alerts

When the pipeline fails, it can post a message to a Slack channel. Follow these steps to enable it.

### 11.1 Create a Slack app

1. Go to **[api.slack.com/apps](https://api.slack.com/apps)** and sign in.
2. Click **Create New App** → **From scratch**.
3. Enter an **App Name** (e.g. `Measurement Alerts`) and select your workspace.
4. Click **Create App**. You’ll land on the app’s Basic Information page.

### 11.2 Add bot permissions

1. In the left sidebar, click **OAuth & Permissions**.
2. Under **Scopes** → **Bot Token Scopes**, click **Add an OAuth Scope**.
3. Search for and add **`chat:write`** (Send messages as @YourAppName).
4. At the top, click **Install to Workspace** (or **Reinstall to Workspace**).
5. Click **Allow** on the permissions screen.
6. Copy the **Bot User OAuth Token** (starts with `xoxb-`). Save it securely — you’ll use it in Step 11.4.

### 11.3 Create a channel and invite the bot

1. In Slack, create a channel (e.g. `#measurement-alerts`) or use an existing one.
2. In the channel, type `/invite @YourAppName` and press Enter to add the bot.
3. Get the **channel ID**:
   - Right-click the channel name → **View channel details** → scroll to the bottom for **Channel ID** (e.g. `C0123456789`), or
   - Open the channel in a browser — the URL ends with `/archives/C0123456789`; that last part is the channel ID.
4. Save the channel ID — you’ll use it in Step 11.4.

### 11.4 Set environment variables and redeploy

1. Open `orchestration/prefect/deployments/deploy.ps1` in Cursor or Notepad.
2. Find the commented Slack lines (after the Supabase vars):
   ```powershell
   # Optional: Slack failure alerts (see orchestration/prefect/SLACK_ALERTS_SETUP.md)
   # $env:SLACK_BOT_TOKEN = "xoxb-your-bot-token"
   # $env:SLACK_ALERT_CHANNEL_ID = "C01234567"
   ```
3. Uncomment both lines and replace with your values:
   ```powershell
   $env:SLACK_BOT_TOKEN = "xoxb-your-actual-token-from-step-11.2"
   $env:SLACK_ALERT_CHANNEL_ID = "C0123456789"
   ```
4. Save the file.
5. Redeploy so the new values are stored:
   ```powershell
   cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
   $env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
   .\orchestration\prefect\deployments\deploy.ps1
   ```
6. Restart the Prefect worker (Ctrl+C in the worker terminal, then run `start_prefect_worker.ps1` again).

### 11.5 Test the alert

1. Temporarily break a dbt model (e.g. add `SELECT * FROM raw.nonexistent_table_xyz`).
2. Run the pipeline: `prefect deployment run daily_pipeline/daily`
3. Check your Slack channel — you should see a message like:
   ```
   :x: *Daily pipeline failed*
   Date: 2025-01-29
   Step: dbt run failed: ...
   ```
4. Restore the dbt model.

**If no message appears:** Check that the bot was invited to the channel, the token starts with `xoxb-`, and the channel ID starts with `C` (no `#`). See `SLACK_ALERTS_SETUP.md` for more troubleshooting.

---

## Summary

| Step | What you did |
|------|--------------|
| 1 | Created `pipeline_runs` table in Supabase |
| 2 | Installed Prefect and dependencies |
| 3 | Got Supabase service role key |
| 4 | Updated `start_prefect_worker.ps1` with your key |
| 5 | Started Prefect server (Terminal 1) |
| 6 | Ran `deploy.ps1` to deploy the daily pipeline |
| 7 | Started Prefect worker (Terminal 2) |
| 8 | Ran the pipeline manually to test |
| 9 | Set Airbyte to sync before 6 AM Eastern |
| 10 | (Optional) Set up Task Scheduler for auto-start |
| 11 | (Optional) Configured Slack failure alerts |

---

## Troubleshooting

**"dbt: command not found"**  
Make sure the worker has dbt on PATH. The `start_prefect_worker.ps1` script adds it. If you run the flow manually, run: `$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"` first.

**"pipeline_runs table doesn't exist"**  
Go back to Step 1 and run the SQL in Supabase.

**"Worker not picking up jobs"**  
Check that the worker is running (Terminal 2) and that the work pool name matches: `default-agent-pool`. In the Prefect UI (http://127.0.0.1:4200), go to Workers and confirm the worker is connected.

**"dbt run failed" in the pipeline**  
Run `dbt run` and `dbt test` manually in the dbt folder. Fix any errors there first; the pipeline will succeed once dbt works locally.

**Slack alert not posting**  
Ensure `SLACK_BOT_TOKEN` (starts with `xoxb-`) and `SLACK_ALERT_CHANNEL_ID` (starts with `C`) are set in `deploy.ps1`, you redeployed after setting them, and the bot was invited to the channel. See Step 11 and `SLACK_ALERTS_SETUP.md` for details.
