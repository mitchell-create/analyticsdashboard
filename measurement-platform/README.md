# Multi-Client Measurement Platform

Repeatable measurement platform that centralizes marketing and sales data from multiple clients in a single shared Supabase, transforms with dbt, surfaces in Metabase, runs GeoLift/CausalImpact experiments, orchestrates with Prefect, and powers per-client Slack Q&A and alerts.

**Architecture:** One Supabase project, all clients. Data separated by `client_slug` column on every table.

**System flow:** Airbyte + Metricool → Supabase (`raw_<client>` schema) → dbt models (with `client_slug`) → Metabase dashboards → GeoLift/CausalImpact runner → Prefect scheduling → Slack Q&A + alerts

---

## Repo structure

| Path | Description |
|------|-------------|
| `ops/client-provision/` | Client setup: `provision_client.py`, `onboarding_checklist.md`, `INGESTION.md` |
| `warehouse/schema/` | Supabase DDL: `000_core.sql` … `065_multi_tenant.sql` |
| `warehouse/seeds/` | Seed data (e.g. `dim_geo_states.csv`) |
| `dbt/` | dbt project: staging + marts models, tests, seeds |
| `services/model-runner/` | GeoLift + CausalImpact runner (Python/R), writes to `experiment_results` |
| `services/slack-bot/` | Slack Bolt app: AI Q&A (NL → SQL), guardrails, daily_alerts, audit |
| `orchestration/prefect/` | Flows: `daily_pipeline`, `run_experiments`, `qa_checks`; `deployments/deploy.sh` |
| `dashboards/metabase/` | Dashboard scripts + SQL + KPI number cards with comparison |

---

## Per-client setup (Shared DB)

All clients share **one Supabase project**. Data is separated by `client_slug`. Run `065_multi_tenant.sql` once to add the column.

**Quick start:**
```powershell
python ops/client-provision/provision_client.py acme --supabase-url "..." --supabase-key "..."
```

**Steps:**
1. **Provision:** Run `provision_client.py <client_slug>` — generates `.env`, runs schema, registers client.
2. **Ingestion:** Configure Airbyte to write to `raw_<client_slug>` schema. See [INGESTION.md](ops/client-provision/INGESTION.md).
3. **dbt:** `dbt run --vars '{client_slug: acme, raw_schema: raw_acme}'`
4. **Metabase:** `python dashboards/metabase/create_mvp_dashboards.py --client acme`; wire `client_slug` filter.
5. **Slack:** Deploy one bot per client with `CLIENT_SLUG=acme` in `.env`.
6. **Prefect:** `CLIENT_SLUG=acme bash orchestration/prefect/deployments/deploy.sh`

Use [ops/client-provision/onboarding_checklist.md](ops/client-provision/onboarding_checklist.md) for the full checklist.

---

## Local dev

- **dbt:** `cd dbt && dbt deps && dbt run --vars '{client_slug: acme, raw_schema: raw_acme}'`
- **Slack bot:** `cd services/slack-bot && npm install && npm run build && npm start` (set `.env` with `CLIENT_SLUG`)
- **Model runner:** `cd services/model-runner && pip install -r requirements.txt` then `CLIENT_SLUG=acme python src/runner.py causalimpact ...`
- **Prefect:** `pip install -r orchestration/prefect/requirements.txt`, set `PREFECT_API_URL` + `CLIENT_SLUG`, run flows

---

## Env

Copy [.env.example](.env.example) to `.env.<client_slug>` and set values. Each `.env` includes `CLIENT_SLUG=<slug>`. Do not commit `.env*` files.

---

## Phases (reference)

0. Client setup (provision script + checklist)
1. Supabase warehouse schema + seeds + `065_multi_tenant.sql`
2. Data ingestion (Airbyte to `raw_<client>` schema + Metricool) — see INGESTION.md
3. dbt modeling layer (staging + marts + tests, with `client_slug` var)
4. Metabase dashboards (MVP spec + KPI number cards with comparison)
5. Incrementality runner (GeoLift/CausalImpact → experiment_results)
6. Slack bot (one per client, Q&A + guardrails + audit)
7. Prefect orchestration (per-client deployments: daily pipeline, experiments, QA)
