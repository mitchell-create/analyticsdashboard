# Slack alerts for pipeline failures

When the daily pipeline fails (Airbyte check, dbt run, or dbt test), it posts a message to a Slack channel. Follow these steps to enable it.

---

## Step 1: Create a Slack app

### 1.1 Open the Slack API page

1. In your browser, go to **[api.slack.com/apps](https://api.slack.com/apps)**.
2. Sign in with your Slack workspace credentials if prompted.
3. You should see a list of existing apps (if any) and a **Create New App** button.

### 1.2 Create the app from scratch

1. Click **Create New App**.
2. Select **From scratch** (not "From manifest").
3. In the dialog:
   - **App Name:** Enter a name like `Measurement Alerts` or `Analytics Pipeline Bot`. This is what users see when the bot posts.
   - **Pick a workspace:** Choose the Slack workspace where you want alerts (e.g. your company workspace).
4. Click **Create App**.
5. You should land on the app’s **Basic Information** page. The left sidebar shows: Basic Information, OAuth & Permissions, Event Subscriptions, etc.

### 1.3 Note the app name

- The app name appears at the top (e.g. "Measurement Alerts"). You’ll use this when inviting the bot to a channel in Step 3.

---

## Step 2: Add bot permissions

### 2.1 Open OAuth & Permissions

1. In the left sidebar of your app’s settings, click **OAuth & Permissions**.
2. You’ll see sections: **OAuth Tokens**, **Redirect URLs**, and **Scopes**.

### 2.2 Add the chat:write scope

1. Scroll to **Scopes**.
2. Under **Bot Token Scopes**, click **Add an OAuth Scope**.
3. In the search box, type `chat:write`.
4. Select **chat:write** from the list. The description says: "Send messages as @YourAppName".
5. You should now see `chat:write` listed under Bot Token Scopes.

### 2.3 Install the app to your workspace

1. Scroll to the top of the page.
2. Click the green **Install to Workspace** button (or **Reinstall to Workspace** if you’ve installed before).
3. A permissions review screen appears. It will list:
   - **chat:write** — Send messages as @YourAppName
4. Click **Allow** to authorize the app.
5. You’ll be redirected back to **OAuth & Permissions**.

### 2.4 Copy the Bot User OAuth Token

1. At the top, under **OAuth Tokens for Your Workspace**, find **Bot User OAuth Token**.
2. Click **Copy** (or select and copy manually).
3. The token starts with `xoxb-` and is long. Example format: `xoxb-XXXX-XXXX-XXXXXXXXXXXXXXXXXXXXXXXX`.
4. **Save it securely** — you’ll paste it into `deploy.ps1` in Step 4. Do not share it or commit it to git.

**Troubleshooting:** If you don’t see "Install to Workspace", you may need workspace admin rights. Ask your Slack admin to create the app or grant you permission.

---

## Step 3: Create a channel and invite the bot

### 3.1 Create a channel (or use an existing one)

1. Open Slack (desktop app or [slack.com](https://slack.com)).
2. In the left sidebar, click the **+** next to **Channels**.
3. Choose **Create a channel**.
4. Enter a name (e.g. `measurement-alerts` or `pipeline-alerts`).
5. Add a description if you like (e.g. "Daily pipeline failure alerts").
6. Choose **Public** or **Private**.
7. Click **Create**.
8. You can invite teammates now or skip — the bot will be added in the next step.

### 3.2 Invite the bot to the channel

1. Open the channel you created (or the one you want to use).
2. In the message box, type: `/invite @` and then start typing your app name (e.g. `Measurement Alerts`).
3. Select your app from the autocomplete list.
4. Press **Enter**.
5. Slack will confirm: "Added @Measurement Alerts to this channel".

**Alternative:** You can also click the channel name at the top → **Integrations** → **Add apps** → find your app → **Add**.

### 3.3 Get the channel ID

The channel ID is a string like `C0123456789` (starts with `C`). You need it for `SLACK_ALERT_CHANNEL_ID`.

**Method A — From Slack desktop/app:**

1. Right-click the channel name in the left sidebar.
2. Click **View channel details** (or **Channel details**).
3. Scroll to the very bottom of the details panel.
4. You’ll see **Channel ID** with a value like `C0123456789`. Click to copy, or select and copy.

**Method B — From the browser URL:**

1. Open the channel in a browser (e.g. `https://yourworkspace.slack.com/archives/C0123456789`).
2. The channel ID is the part after `/archives/` (e.g. `C0123456789`).
3. Copy that value.

**Method C — Using Slack’s "Copy link":**

1. Right-click the channel name → **Copy link**.
2. The link looks like: `https://yourworkspace.slack.com/archives/C0123456789`.
3. The channel ID is the last segment (`C0123456789`).

**Save this value** — you’ll use it as `SLACK_ALERT_CHANNEL_ID` in Step 4.

---

## Step 4: Set environment variables and redeploy

### 4.1 Edit deploy.ps1

1. Open this file in Cursor or Notepad:
   ```
   C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\orchestration\prefect\deployments\deploy.ps1
   ```
2. Find the commented Slack lines (near the top, after the Supabase vars):
   ```powershell
   # Optional: Slack failure alerts (see orchestration/prefect/SLACK_ALERTS_SETUP.md)
   # $env:SLACK_BOT_TOKEN = "xoxb-your-bot-token"
   # $env:SLACK_ALERT_CHANNEL_ID = "C01234567"
   ```
3. Remove the `#` to uncomment both lines.
4. Replace the placeholder values:
   - `$env:SLACK_BOT_TOKEN = "xoxb-your-actual-token-here"` — paste the token from Step 2.4.
   - `$env:SLACK_ALERT_CHANNEL_ID = "C0123456789"` — paste the channel ID from Step 3.3.
5. Save the file.

**Security:** `deploy.ps1` may contain secrets. Add it to `.gitignore` if you don’t want it committed, or use a separate config file that’s not in git.

### 4.2 Run the deploy script

1. Open **PowerShell**.
2. Go to the repo root:
   ```powershell
   cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
   ```
3. Ensure Prefect API URL is set (if not already):
   ```powershell
   $env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
   ```
4. Run the deploy script:
   ```powershell
   .\orchestration\prefect\deployments\deploy.ps1
   ```
5. You should see output like:
   ```
   ==> Prefect 3 deploy (repo: ...)
   Deployed: daily_pipeline (daily at 6:00 AM Eastern)
   ```
6. The Slack token and channel ID are now stored in the Prefect deployment’s job variables.

### 4.3 Restart the Prefect worker

The worker must be restarted so it uses the updated deployment:

1. In the terminal where the worker is running, press **Ctrl+C** to stop it.
2. Start it again using your usual method, e.g.:
   ```powershell
   cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
   .\orchestration\prefect\startup\start_prefect_worker.ps1
   ```
   Or, if you use Task Scheduler, the next run will use the new deployment.

**Note:** If you don’t restart the worker, the next scheduled run (e.g. 6 AM) will still use the new deployment — Prefect workers fetch job definitions when they pick up a run. Restarting is recommended to avoid any caching.

---

## Step 5: Test it

### 5.1 Option A: Trigger a real failure (recommended)

1. Temporarily break a dbt model so `dbt run` fails. For example, open a staging model and add invalid SQL:
   ```sql
   SELECT * FROM raw.nonexistent_table_xyz
   ```
2. Run the pipeline manually:
   ```powershell
   cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
   $env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
   $env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"
   prefect deployment run daily_pipeline/daily
   ```
3. Within a few seconds, check your Slack channel. You should see a message like:
   ```
   :x: *Daily pipeline failed*
   Date: 2025-01-29
   Step: dbt run failed: Database Error in model stg_xxx ...
   ```
4. Restore the dbt model to its original state.

### 5.2 Option B: Run without breaking anything

If the pipeline succeeds, no Slack message is sent (alerts are only on failure). To verify the integration without breaking dbt, you can add a temporary test: in `daily_pipeline.py`, add a `raise RuntimeError("test")` right after the flow starts, run the deployment, then remove it.

### 5.3 If no message appears

- **Check the channel:** Ensure you’re looking at the correct channel and that the bot was invited.
- **Check the token:** Ensure `SLACK_BOT_TOKEN` starts with `xoxb-` and has no extra spaces or quotes.
- **Check the channel ID:** It should start with `C` and be 9–11 characters. No `#` prefix.
- **Check worker logs:** The worker terminal may show `Slack alert failed: ...` if the API call failed.
- **Check Slack app:** In [api.slack.com/apps](https://api.slack.com/apps), confirm the app is installed and has `chat:write`.

---

## Optional: Run worker with Slack vars directly

If you prefer not to store Slack credentials in the deployment (e.g. for security or different envs per worker):

1. Open `orchestration/prefect/startup/start_prefect_worker.ps1`.
2. Add these lines before the `prefect worker start` command:
   ```powershell
   $env:SLACK_BOT_TOKEN = "xoxb-your-token"
   $env:SLACK_ALERT_CHANNEL_ID = "C01234567"
   ```
3. In `deploy.ps1`, leave the Slack lines commented (or remove them from `prefect.yaml` job_variables).
4. The worker’s environment will provide the vars to the flow. For process workers, deployment job_variables override worker env, so to use the worker env you must not set Slack vars in the deployment.
