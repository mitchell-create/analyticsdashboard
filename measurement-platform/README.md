# Multi-Client Measurement Platform

Repeatable measurement platform (one DB per client) that centralizes marketing and sales data in Supabase, transforms it with dbt, surfaces it in Metabase, runs GeoLift/CausalImpact experiments, orchestrates with Prefect, and powers Slack Q&A and alerts.

**System flow:** Airbyte + Metricool → Supabase → dbt models → Metabase dashboards → GeoLift/CausalImpact runner → Prefect scheduling → Slack Q&A + alerts

---

## Repo structure

| Path | Description |
|------|-------------|
| `ops/client-provision/` | Client setup: `provision_client.sh`, `onboarding_checklist.md`, `INGESTION.md` |
| `warehouse/schema/` | Supabase DDL: `000_core.sql` … `050_quality.sql` |
| `warehouse/seeds/` | Seed data (e.g. `dim_geo_states.csv`) |
| `dbt/` | dbt project: staging + marts models, tests, seeds |
| `services/model-runner/` | GeoLift + CausalImpact runner (Python/R), writes to `experiment_results` |
| `services/slack-bot/` | Slack Bolt app: AI Q&A (NL → SQL), guardrails, daily_alerts, audit |
| `orchestration/prefect/` | Flows: `daily_pipeline`, `run_experiments`, `qa_checks`; `deployments/deploy.sh` |
| `dashboards/metabase/` | `MVP_dashboard_spec.md` (marts-only) |

---

## Per-client setup (Pattern B)

1. **Provision client:** Run `ops/client-provision/provision_client.sh <client_slug>` and follow prompts (or create Supabase project manually).
2. **Apply warehouse schema:** Execute `warehouse/schema/*.sql` in order (000 → 050) in the client’s Supabase SQL Editor.
3. **Ingestion:** Configure Airbyte (Meta, Google, TikTok Ads, Shopify, Klaviyo) and Metricool (TikTok organic) per [ops/client-provision/INGESTION.md](ops/client-provision/INGESTION.md). Backfill 90 days; nightly refresh last 14–30 days.
4. **dbt:** Copy `dbt/profiles.yml.template` to `profiles.yml`, set `SUPABASE_DB_*` for this client. Run `dbt seed`, `dbt run`, `dbt test`.
5. **Metabase:** Add client Supabase as data source; build dashboards from [dashboards/metabase/MVP_dashboard_spec.md](dashboards/metabase/MVP_dashboard_spec.md) (marts only).
6. **Slack:** Create channel; invite bot; set `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `SLACK_ALERT_CHANNEL_ID`; set `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_DB_URL` for Q&A.
7. **Prefect:** Set env for this client; run `orchestration/prefect/deployments/deploy.sh` and apply deployments; start worker.

Use [ops/client-provision/onboarding_checklist.md](ops/client-provision/onboarding_checklist.md) for the full checklist.

---

## Local dev

- **dbt:** `cd dbt && dbt deps && dbt run && dbt test`
- **Slack bot:** `cd services/slack-bot && npm install && npm run build && npm start` (set `.env` from `.env.example`)
- **Model runner:** `cd services/model-runner && pip install -r requirements.txt` then `python src/runner.py geolift <slug> <start> <end> <treatment_geos> <holdout_geos>` or `causalimpact ...`
- **Prefect:** `pip install -r orchestration/prefect/requirements.txt`, set `PREFECT_API_URL`, run flows with `prefect deployment run daily_pipeline/daily` or `python orchestration/prefect/flows/daily_pipeline.py`

---

## Env

Copy [.env.example](.env.example) to `.env` and set values per client. Do not commit `.env`.

---

## Phases (reference)

0. Client setup (provision script + checklist)  
1. Supabase warehouse schema + seeds  
2. Data ingestion (Airbyte + Metricool) — see INGESTION.md  
3. dbt modeling layer (staging + marts + tests)  
4. Metabase dashboards (MVP spec)  
5. Incrementality runner (GeoLift/CausalImpact → experiment_results)  
6. Slack bot (Q&A + guardrails + audit)  
7. Prefect orchestration (daily pipeline, experiments, QA + deploy)
