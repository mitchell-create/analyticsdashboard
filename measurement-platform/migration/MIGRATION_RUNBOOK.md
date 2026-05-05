# Migration Runbook — Supabase → Local Postgres on Dedicated PC

A top-to-bottom checklist for moving the warehouse off Supabase. Do **not** delete anything on Supabase until Step 11 passes for a full week.

**Total active time:** ~3-4 hours across one or two sessions. Most of it is waiting on installs.

**Architecture after migration:**
- **Dedicated PC** (always-on): Postgres, Airbyte, Prefect, Slack bot, Metabase, dbt, rclone backups
- **Work PC**: dev environment only (Claude Code, git, editor)
- **Tailscale**: links the two PCs over a private mesh
- **Google Drive**: nightly encrypted Postgres dumps

---

## Execution model

This runbook is designed to be executed by **Codex on the dedicated PC**. After each step:

1. Run the **Action** commands.
2. Run the **Verify** commands and check **Expected** output.
3. Output a phase report to Mitchell using this template:

```
PHASE <n> COMPLETE — <name>

Action results:
- <command> → <result>

Verifications:
- <check> → PASS/FAIL (<actual>)

Issues:
- <anything unexpected>

Ready for Phase <n+1>? (await "y" before proceeding)
```

**Do NOT auto-advance phases.** Wait for Mitchell to confirm before moving forward. If a verification fails or anything looks wrong, stop and report rather than improvising.

See `AGENTS.md` at the repo root for project-wide rules and conventions.

---

## Pre-flight — verify on work PC

- [ ] Confirm `measurement-platform/.env` has current `SUPABASE_DB_URL` (used to dump from Supabase)
- [ ] Confirm `client_ad_accounts.csv` is up to date
- [ ] Push any uncommitted work to git so dedicated PC can pull a clean checkout

```bash
cd C:/Users/ReadyPlayerOne/analyticsdashboard
git status
git push
```

---

## Step 1 — Bootstrap dedicated PC (~30-60 min, mostly waiting)

On the dedicated PC, in **elevated PowerShell**:

- [ ] Clone the repo first to get the bootstrap script
  ```powershell
  cd $HOME
  mkdir repos -Force; cd repos
  git clone https://github.com/<your-fork>/analyticsdashboard.git
  cd analyticsdashboard\measurement-platform\migration
  ```
- [ ] Run bootstrap (installs Postgres, Docker, Python, Node, Tailscale, rclone, R, abctl, Metabase)
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\bootstrap-dedicated-pc.ps1
  ```
- [ ] Restart PowerShell (so PATH picks up new installs)

---

## Step 2 — Initialize Postgres (~10 min)

- [ ] During Postgres install, you set a `postgres` superuser password — note it.
- [ ] Create the `analytics` database and a dedicated app user:
  ```powershell
  $env:PGPASSWORD = "<superuser-pw>"
  & "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE analytics;"
  & "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h localhost -c "CREATE USER app WITH PASSWORD '<choose-app-pw>';"
  & "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h localhost -c "GRANT ALL ON DATABASE analytics TO app;"
  & "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d analytics -c "GRANT ALL ON SCHEMA public TO app;"
  ```
- [ ] Edit `C:\Program Files\PostgreSQL\16\data\postgresql.conf`:
  - `listen_addresses = '*'`
- [ ] Edit `C:\Program Files\PostgreSQL\16\data\pg_hba.conf`, add line for Tailscale subnet (after Step 3):
  ```
  host    all   all   100.64.0.0/10   scram-sha-256
  ```
- [ ] Restart Postgres service:
  ```powershell
  Restart-Service postgresql-x64-16
  ```

---

## Step 3 — Tailscale on both PCs (~10 min)

- [ ] On dedicated PC: launch Tailscale → sign in with same account
- [ ] On work PC: install Tailscale (`winget install Tailscale.Tailscale`) → sign in
- [ ] Note the dedicated PC's Tailscale IP (Tailscale tray icon → "This device") — looks like `100.x.y.z`
- [ ] From work PC, verify connectivity:
  ```bash
  ping <dedicated-pc-tailscale-ip>
  ```

---

## Step 4 — Migrate data (~15-30 min)

From the **dedicated PC** (since it has the destination Postgres locally):

- [ ] Set source connection string:
  ```powershell
  $env:SUPABASE_DB_URL = "<paste from work PC's .env>"
  ```
- [ ] Dump the schemas you actually need (skip Supabase plumbing):
  ```powershell
  & "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" `
      --no-owner --no-acl `
      --schema=public --schema=public_marts --schema=raw `
      --format=custom --jobs=4 `
      --file=$HOME\warehouse.dump `
      $env:SUPABASE_DB_URL
  ```
- [ ] Restore to local:
  ```powershell
  $env:PGPASSWORD = "<superuser-pw>"
  & "C:\Program Files\PostgreSQL\16\bin\pg_restore.exe" `
      --no-owner --no-acl --jobs=4 `
      -U postgres -h localhost -d analytics `
      $HOME\warehouse.dump
  ```
- [ ] Verify counts match source:
  ```powershell
  & "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d analytics -c `
      "SELECT schemaname, COUNT(*) AS tables FROM pg_tables WHERE schemaname IN ('raw','public','public_marts') GROUP BY schemaname ORDER BY schemaname;"
  ```
  Expected (post-region-drop): raw ~44 tables, public_marts ~16, public ~18.

---

## Step 5 — Repoint services (~30 min)

**Note:** Phase 0 Option A is already applied — all DB access goes through `pg`/`psycopg2` direct, no Supabase REST. Only the connection string needs to change.

**Action — set the new connection string everywhere:**

The new connection string format:
```
postgresql://app:<app-pw>@127.0.0.1:5432/analytics
```

(Use `127.0.0.1` for services running on the dedicated PC. The Tailscale IP is only for the work PC reaching this DB remotely — see Step 7 for Metabase.)

### 5a. Create `.env` files from captured secrets

`.env` files are gitignored — Codex will not find them in the cloned repo. Mitchell needs to provide the secrets captured from the work PC's `.env` and `clients.json`. If they are not yet on this PC, STOP and ask for them.

Required environment variables:
```
# measurement-platform/.env
SUPABASE_DB_URL=postgresql://app:<app-pw>@127.0.0.1:5432/analytics
SLACK_BOT_TOKEN=<from-password-manager>
SLACK_APP_TOKEN=<from-password-manager>
SLACK_SIGNING_SECRET=<from-password-manager>
SLACK_ALERT_CHANNEL_ID=<from-password-manager>
OPENAI_API_KEY=<from-password-manager>
KLAVIYO_API_KEY_EXPAND=<from-password-manager>
KLAVIYO_API_KEY_CHUBBLE=<from-password-manager>
# ...one per client
DBT_PROJECT_DIR=$HOME\repos\analyticsdashboard\measurement-platform\dbt
```

```
# measurement-platform/services/slack-bot/.env
SUPABASE_DB_URL=postgresql://app:<app-pw>@127.0.0.1:5432/analytics
SLACK_BOT_TOKEN=<same-as-above>
SLACK_APP_TOKEN=<same-as-above>
SLACK_SIGNING_SECRET=<same-as-above>
OPENAI_API_KEY=<same-as-above>
```

### 5b. Recreate `clients.json` (slack-bot multi-client config)

```
[
  { "slug": "expand",       "displayName": "Expand Furniture", "dbUrl": "postgresql://app:<app-pw>@127.0.0.1:5432/analytics" },
  { "slug": "chubble",      "displayName": "Chubble Gum",      "dbUrl": "postgresql://app:<app-pw>@127.0.0.1:5432/analytics" },
  { "slug": "crazy_rumors", "displayName": "Crazy Rumors",     "dbUrl": "postgresql://app:<app-pw>@127.0.0.1:5432/analytics" },
  { "slug": "zoka",         "displayName": "Zoka Coffee",      "dbUrl": "postgresql://app:<app-pw>@127.0.0.1:5432/analytics" },
  { "slug": "babybay",      "displayName": "babybay",          "dbUrl": "postgresql://app:<app-pw>@127.0.0.1:5432/analytics" },
  { "slug": "secondkind",   "displayName": "Secondkind",       "dbUrl": "postgresql://app:<app-pw>@127.0.0.1:5432/analytics" }
]
```

Save to `$HOME\repos\analyticsdashboard\measurement-platform\services\slack-bot\clients.json`. Confirm `.gitignore` already excludes it (`grep clients.json .gitignore` should match).

### 5c. Create `dbt/profiles.yml`

```yaml
analytics:
  target: dev
  outputs:
    dev:
      type: postgres
      host: 127.0.0.1
      port: 5432
      user: app
      password: <app-pw>
      dbname: analytics
      schema: public_marts
      threads: 4
```

Save to `$HOME\repos\analyticsdashboard\measurement-platform\dbt\profiles.yml`.

**Verify:**
```powershell
# .env files exist and have SUPABASE_DB_URL set
Test-Path "$HOME\repos\analyticsdashboard\measurement-platform\.env"
Test-Path "$HOME\repos\analyticsdashboard\measurement-platform\services\slack-bot\.env"
Test-Path "$HOME\repos\analyticsdashboard\measurement-platform\services\slack-bot\clients.json"
Test-Path "$HOME\repos\analyticsdashboard\measurement-platform\dbt\profiles.yml"

# Confirm gitignore protects them
cd $HOME\repos\analyticsdashboard
git check-ignore measurement-platform/.env measurement-platform/services/slack-bot/.env measurement-platform/services/slack-bot/clients.json measurement-platform/dbt/profiles.yml
# Expected: all four paths echoed (means they ARE ignored)

# DB connection works
$env:PGPASSWORD = "<app-pw>"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U app -h 127.0.0.1 -d analytics -c "SELECT 1 AS ok"
# Expected: returns "ok | 1"
```

**Expected:** all four config files exist, all are gitignored, DB returns `1`.

---

## Step 6 — Repoint Airbyte destination (~15 min)

On the dedicated PC, you'll re-install Airbyte (kind cluster, fresh). The previous Airbyte state stays on the work PC and is decommissioned at the end.

- [ ] `& "$HOME\abctl-v0.31.0-windows-amd64\abctl.exe" local install`
- [ ] Wait for `http://localhost:8000`, log in
- [ ] Recreate sources (Meta after re-auth cooldown ends, Google, TikTok, Klaviyo direct sync stays as Python script)
- [ ] **Destination**: add Postgres → host `localhost`, port `5432`, db `analytics`, user `app`, password set, schema `raw`
- [ ] Recreate connections, set replication frequency to manual (we trigger via Prefect)

(If Airbyte connection state on the work PC is too valuable to lose, we can dump/restore the Airbyte database too — separate ticket.)

---

## Step 7 — Repoint Metabase (~10 min)

- [ ] Stop Metabase on the work PC (if running)
- [ ] On dedicated PC, start Metabase:
  ```powershell
  $env:MB_DB_FILE = "$HOME\metabase\metabase.db"
  $env:TEMP = "C:\T"   # Per Windows path-length quirk
  java -jar $HOME\metabase\metabase.jar
  ```
- [ ] In browser → http://localhost:3000 → re-add admin user
- [ ] Add new database: PostgreSQL → host `localhost` → db `analytics` → user `app`
- [ ] Migrate dashboards: copy `metabase.db` from work PC, OR rebuild from `dashboards/metabase/sql/` (faster + cleaner)

---

## Step 8 — Smoke test (~15 min)

Run each in sequence. **All must pass before proceeding.** If any fails, stop and report exact error.

### 8a. dbt builds clean
```powershell
cd $HOME\repos\analyticsdashboard\measurement-platform\dbt
dbt deps
dbt run
dbt test
```
**Expected:** dbt run reports `Completed successfully`, dbt test reports 0 failures (warnings OK).

### 8b. Slack bot type-checks and boots
```powershell
cd $HOME\repos\analyticsdashboard\measurement-platform\services\slack-bot
npm install
npx tsc --noEmit
# Expected: no output, exit code 0

# Brief boot test (kill after 10s — we just want to confirm it connects to DB and Slack)
Start-Process -NoNewWindow -FilePath "npm" -ArgumentList "run","dev" -RedirectStandardOutput slack-bot.log -RedirectStandardError slack-bot.err
Start-Sleep -Seconds 15
Stop-Process -Name "node" -ErrorAction SilentlyContinue
Get-Content slack-bot.log
```
**Expected:** log contains `⚡️ Bolt app is running` (or similar startup line) and no `ECONNREFUSED` / `password authentication failed`.

### 8c. Prefect flow imports cleanly
```powershell
cd $HOME\repos\analyticsdashboard\measurement-platform\orchestration\prefect\flows
python -c "import daily_pipeline, qa_checks, run_experiments, scheduled_reports; print('All flows imported OK')"
```
**Expected:** prints `All flows imported OK`.

### 8d. Chubble report dry-run produces non-zero data
```powershell
cd $HOME\repos\analyticsdashboard\measurement-platform
python orchestration\chubble_report.py --dry-run
```
**Expected:** output starts with `:bar_chart: *Chubble Gum Performance Report*` and shows non-zero spend / revenue values for at least one platform. If all zeros, the warehouse migrated empty for chubble — STOP and investigate.

### 8e. Row-count parity vs Supabase

Compare a few key tables between the source (Supabase) and destination (local) to confirm migration completeness. Use the Supabase connection string from Mitchell's secrets only for this check, then discard.

```powershell
# Local
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U app -h 127.0.0.1 -d analytics -c `
    "SELECT 'public_marts.fact_kpi_daily' AS t, COUNT(*) FROM public_marts.fact_kpi_daily UNION ALL SELECT 'raw.chubble_orders', COUNT(*) FROM raw.chubble_orders UNION ALL SELECT 'raw.meta_ads_insights', COUNT(*) FROM raw.meta_ads_insights;"

# Supabase (paste source URL via env)
$env:PGPASSWORD = "<from-supabase-conn-string>"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" "<full-supabase-conn-string>" -c `
    "SELECT 'public_marts.fact_kpi_daily' AS t, COUNT(*) FROM public_marts.fact_kpi_daily UNION ALL SELECT 'raw.chubble_orders', COUNT(*) FROM raw.chubble_orders UNION ALL SELECT 'raw.meta_ads_insights', COUNT(*) FROM raw.meta_ads_insights;"
```
**Expected:** counts match exactly. If off by a small amount, recent rows may have synced post-dump — note the diff but acceptable. If off by >5%, STOP and re-dump.

---

## Step 9 — Set up nightly backups (~15 min)

- [ ] Configure rclone to talk to Drive:
  ```powershell
  rclone config
  # New remote → "gdrive" → drive → follow OAuth flow → use service account or personal
  ```
- [ ] Test:
  ```powershell
  rclone lsd gdrive:
  ```
- [ ] Drop in `backup-warehouse.ps1` (separate file in this directory)
- [ ] Register Windows scheduled task to run nightly at 3am:
  ```powershell
  $action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-File $HOME\repos\analyticsdashboard\measurement-platform\migration\backup-warehouse.ps1"
  $trigger = New-ScheduledTaskTrigger -Daily -At 3am
  Register-ScheduledTask -TaskName "Warehouse Backup" -Action $action -Trigger $trigger -RunLevel Highest
  ```
- [ ] **Test the restore path once** — pull yesterday's backup, restore to a `analytics_restore_test` DB, count rows. Trust nothing until restore is verified.

---

## Step 10 — Run dual for 7 days

- [ ] Keep Supabase running, untouched
- [ ] Use only the dedicated PC for live work
- [ ] Daily check: do reports / dashboards / Slack queries still work?
- [ ] If anything breaks, the Supabase connection string is one env-var revert away

---

## Step 11 — Decommission Supabase (after 7 clean days)

- [ ] Final pg_dump from Supabase → archive to Drive (`supabase-final-<date>.dump`) — paranoia backup
- [ ] Pause the Supabase project (stays restorable for 7 days)
- [ ] After another 7 days of green: delete project or downgrade to free tier

---

## Rollback plan

If anything breaks during the 7-day dual run:
1. Revert `SUPABASE_DB_URL` (and dbt `profiles.yml`) to the original Supabase URL
2. Restart services
3. You're back on Supabase — debug the dedicated PC issue offline

The local Postgres data isn't going anywhere, so you can iterate on it without time pressure.

---

## Open questions for migration day

- [ ] Are we doing Option A (rewrite REST inserts) or Option B (self-host PostgREST)? Default: Option A.
- [ ] Migrate Airbyte connection state, or recreate from scratch? Default: recreate (cleaner; Meta re-auth pending anyway).
- [ ] Migrate Metabase dashboards via DB copy, or rebuild from SQL files? Default: rebuild from SQL files (catches drift).
