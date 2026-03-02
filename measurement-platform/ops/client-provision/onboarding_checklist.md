# Client onboarding checklist (Pattern B — 1 DB per client)

Use this checklist for each new client. Replace `CLIENT_SLUG` with the client identifier (e.g. `acme`).

**Quick start:** Run the provisioning script to automate steps 1–5:

```powershell
cd ops\client-provision
python provision_client.py CLIENT_SLUG --supabase-url "https://xxx.supabase.co" --supabase-key "eyJ..."
```

---

## 1. Supabase (database)

- [ ] Create Supabase project (e.g. `measurement-CLIENT_SLUG`)
- [ ] Save project URL and service role key securely
- [ ] Run warehouse schema migrations: `000_core.sql` → `060_rls.sql`
  - Automated: `provision_client.py` runs via psql if `--supabase-db-url` is set
  - Manual: paste each file into Supabase SQL Editor
- [ ] Load seed data: `dbt seed` (after dbt is configured)
- [ ] Confirm tables exist: facts, dims, events, experiments, quality tables

## 2. Airbyte (data ingestion)

- [ ] Create or assign Airbyte workspace for this client
- [ ] Add source — Meta Ads (credentials, ad account)
- [ ] Add source — Google Ads (credentials, customer ID)
- [ ] Add source — TikTok Ads (credentials, advertiser ID)
- [ ] Add source — Shopify (store URL, API token)
- [ ] Add source — Klaviyo (API key)
- [ ] Set destination — Supabase (this client's connection string)
- [ ] Map streams to raw tables / default namespace
- [ ] Set sync schedule (e.g. daily)
- [ ] Run initial sync; backfill 90 days (then expand to 12–24 months as needed)
- [ ] Document refresh window (e.g. last 14–30 days nightly)
- [ ] See: `ops/client-provision/INGESTION.md`

## 3. Metricool (TikTok organic — optional)

- [ ] Connect TikTok account for this client
- [ ] Configure daily export or API sync to Supabase
- [ ] Confirm data lands in staging table for dbt
- [ ] Verify date range and metrics (views, engagement, etc.)

## 4. dbt (transform)

- [ ] Set SUPABASE_DB_* env vars from `.env.CLIENT_SLUG`
- [ ] `cd dbt && dbt deps && dbt seed && dbt run && dbt test`
- [ ] Confirm marts are populated: `fact_spend_daily`, `fact_kpi_daily`, etc.

## 5. Metabase (dashboards)

- [ ] Add this client's Supabase as a database in Metabase
  - Name it: `measurement-CLIENT_SLUG`
  - Connect only to schema where dbt marts live
- [ ] Create dashboards:
  ```powershell
  cd dashboards\metabase
  $env:METABASE_EMAIL = "admin@example.com"
  $env:METABASE_PASSWORD = "password"
  python create_mvp_dashboards.py --client CLIENT_SLUG --database-name "measurement-CLIENT_SLUG"
  python create_kpi_number_cards.py --client CLIENT_SLUG --database-name "measurement-CLIENT_SLUG"
  ```
- [ ] Wire date filters to all cards (see `KPI_NUMBER_CARDS_SETUP.md`)
- [ ] Share dashboard links with client stakeholders

## 6. Slack bot (one bot per client)

Each client gets its **own Slack bot process** with its own env vars. This ensures complete data isolation.

- [ ] Create Slack channel (e.g. `#measurement-CLIENT_SLUG`)
- [ ] Create or reuse Slack app; add bot to this channel
- [ ] Copy `services/slack-bot/.env.example` → `.env.CLIENT_SLUG`
- [ ] Set in `.env.CLIENT_SLUG`:
  - `SLACK_BOT_TOKEN` — this client's Slack app bot token
  - `SLACK_SIGNING_SECRET` — this client's Slack app signing secret
  - `SUPABASE_URL` — this client's Supabase URL
  - `SUPABASE_SERVICE_KEY` — this client's Supabase service key
  - `SUPABASE_DB_URL` — this client's Supabase DB connection string
  - `PORT` — unique port per client (3001, 3002, etc.)
- [ ] Deploy:
  ```powershell
  cd services\slack-bot
  npm install && npm run build
  # Copy env and start:
  copy .env.CLIENT_SLUG .env
  node dist/index.js
  # For production: use PM2, systemd, or Docker
  ```
- [ ] Test Q&A: "Spend in Texas last month?"
- [ ] Confirm daily pipeline alerts post to this channel on failure

## 7. Prefect (orchestration — per client)

- [ ] Set env vars for this client in a dedicated terminal:
  ```powershell
  $env:SUPABASE_URL = "..."
  $env:SUPABASE_SERVICE_KEY = "..."
  $env:SLACK_BOT_TOKEN = "..."
  $env:SLACK_ALERT_CHANNEL_ID = "..."
  ```
- [ ] Deploy flows for this client:
  ```powershell
  $env:CLIENT_SLUG = "CLIENT_SLUG"
  bash orchestration/prefect/deployments/deploy.sh
  # Or on Windows, run the PowerShell equivalent from deploy.ps1
  ```
- [ ] Apply deployments: `prefect deployment apply *.yaml`
- [ ] Start worker: `prefect worker start --pool default-pool`
- [ ] Test: `prefect deployment run daily_pipeline/CLIENT_SLUG-daily`
- [ ] Confirm failure notifications go to Slack

## 8. Model runner (GeoLift / CausalImpact)

- [ ] Set SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_DB_URL for this client
- [ ] Test CausalImpact:
  ```powershell
  cd services\model-runner\src
  python runner.py causalimpact test-campaign 2025-01-01 2025-02-28 2025-01-15 revenue
  ```
- [ ] Test GeoLift (requires geo-level data in `fact_kpi_geo_daily`):
  ```powershell
  python runner.py geolift test-geo 2025-01-01 2025-02-28 "TX,CA" "NY,FL"
  ```
- [ ] Verify results in `experiment_results` table
- [ ] Confirm Metabase Experiment Results dashboard shows data

---

## Sign-off

- [ ] All items above completed for `CLIENT_SLUG`
- [ ] First full daily pipeline run successful
- [ ] Stakeholders have Metabase access and Slack channel invite

**Completed by:** _________________ **Date:** _________________
