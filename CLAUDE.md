# Analytics Dashboard — Claude Code Context

## Project Overview
Multi-client measurement platform: Airbyte + Metricool -> Supabase -> dbt -> Metabase dashboards -> GeoLift/CausalImpact -> Prefect scheduling -> Slack Q&A + alerts.

## Key Paths
- `measurement-platform/dbt/` — dbt models (staging + marts)
- `measurement-platform/dashboards/metabase/` — Metabase SQL queries & dashboard specs
- `measurement-platform/services/slack-bot/` — Slack bot (Node.js/TypeScript)
- `measurement-platform/services/model-runner/` — GeoLift/CausalImpact runner (Python + R)
- `measurement-platform/orchestration/prefect/` — Prefect flows & deployments
- `measurement-platform/warehouse/schema/` — Supabase DDL files
- `measurement-platform/ops/` — Client provisioning scripts

## Local Services (browser-accessible)
- **Metabase**: http://localhost:3000 (BI dashboards)
- **Prefect UI**: http://localhost:4200 (orchestration)
- **Supabase Studio**: via Supabase dashboard (cloud)
- **Slack Bot**: http://localhost:3001 (use ngrok for Slack events)

## Browser Access
Use the Google Chrome browser integration (not Playwright) to:
- Navigate to and interact with Metabase dashboards at http://localhost:3000
- Monitor Prefect flow runs in the Prefect UI at http://localhost:4200
- Access any local web service running on localhost

## Commands
- **dbt**: `cd measurement-platform/dbt && dbt deps && dbt run && dbt test`
- **Slack bot**: `cd measurement-platform/services/slack-bot && npm run dev`
- **Prefect**: `prefect server start` (then `prefect deployment run ...`)
- **Model runner**: `cd measurement-platform/services/model-runner && python src/runner.py`

## Environment
- Copy `measurement-platform/.env.example` to `.env` and fill in secrets
- Copy `measurement-platform/dbt/profiles.yml.template` to `profiles.yml`
- Never commit `.env` or `profiles.yml`
