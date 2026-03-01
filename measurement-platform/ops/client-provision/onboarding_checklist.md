# Client onboarding checklist (Pattern B — 1 DB per client)

Use this checklist for each new client. Replace `CLIENT_SLUG` with the client identifier (e.g. `acme`).

---

## 1. Supabase (database)

- [ ] Create Supabase project (e.g. `measurement-CLIENT_SLUG`)
- [ ] Save project URL and service role key securely
- [ ] Run warehouse schema migrations in order: `000_core.sql` → `050_quality.sql`
- [ ] Load seed data: `dim_geo_states.csv` into `dim_geo` (or run `dbt seed` after dbt is configured)
- [ ] Confirm tables exist: facts, dims, events, experiments, quality tables

## 2. Airbyte (ingestion)

- [ ] Create or assign Airbyte workspace for this client
- [ ] Add source — Meta Ads (credentials, ad account)
- [ ] Add source — Google Ads (credentials, customer ID)
- [ ] Add source — TikTok Ads (credentials, advertiser ID)
- [ ] Add source — Shopify (store URL, API token)
- [ ] Add source — Klaviyo (API key)
- [ ] Set destination — Supabase (this client’s connection string)
- [ ] Map streams to raw tables / default namespace
- [ ] Set sync schedule (e.g. daily)
- [ ] Run initial sync; backfill 90 days (then expand to 12–24 months as needed)
- [ ] Document refresh window (e.g. last 14–30 days nightly)

## 3. Metricool (TikTok organic)

- [ ] Connect TikTok account for this client
- [ ] Configure daily export or API sync to Supabase
- [ ] Confirm data lands in `fact_tiktok_organic_daily` or designated staging table for dbt
- [ ] Verify date range and metrics (views, engagement, etc.)

## 4. dbt (transform)

- [ ] Copy `profiles.yml.template` to `profiles.yml` (or use env-based profile)
- [ ] Set Supabase target for this client (connection details)
- [ ] Run `dbt deps` and `dbt run` (staging + marts)
- [ ] Run `dbt test`; fix any failures
- [ ] Confirm marts are populated: `fact_spend_daily`, `fact_kpi_daily`, `fact_tiktok_organic_daily`, etc.

## 5. Metabase (dashboards)

- [ ] Add Supabase as data source (this client’s DB)
- [ ] Connect only to schema/database where dbt marts live (no raw Airbyte tables for reporting)
- [ ] Clone or create dashboards from MVP spec: Executive Overview, Channel Performance, Organic TikTok + Email Context, Experiment Results
- [ ] Set up filters (e.g. date range, client) if multi-tenant UI
- [ ] Share links with client stakeholders

## 6. Slack (alerts + Q&A)

- [ ] Create Slack channel (e.g. `#measurement-CLIENT_SLUG`)
- [ ] Invite Slack bot app; grant channel access
- [ ] Configure bot env: Supabase URL/key for this client, allowlisted tables
- [ ] Test Q&A: e.g. “Spend in Texas last month?”
- [ ] Confirm daily pipeline alerts post to this channel on failure

## 7. Prefect (orchestration)

- [ ] Create Prefect deployment for this client (or use one deployment with client env vars)
- [ ] Set env: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `AIRBYTE_*`, `METRICOOL_*`, `SLACK_*`, etc.
- [ ] Schedule daily pipeline (Airbyte sync check → dbt run/test → QA checks → Slack alerts)
- [ ] Schedule or trigger experiment flow (GeoLift / CausalImpact) as needed
- [ ] Confirm failure notifications go to Slack

## 8. Model runner (GeoLift / CausalImpact)

- [ ] Configure runner to use this client’s Supabase (read marts, write `experiment_results`)
- [ ] Run a test GeoLift or CausalImpact experiment; confirm results in `experiment_results`
- [ ] Verify Metabase Experiment Results dashboard shows data

---

## Sign-off

- [ ] All items above completed for `CLIENT_SLUG`
- [ ] First full daily pipeline run successful
- [ ] Stakeholders have Metabase access and Slack channel invite

**Completed by:** _________________ **Date:** _________________
