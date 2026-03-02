# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Multi-client measurement platform connecting marketing/sales data through Supabase, dbt, Prefect, Metabase, and a Slack bot. See `measurement-platform/README.md` for full architecture and repo structure.

### Services

| Service | Language | Location | Run command |
|---|---|---|---|
| **dbt** | SQL | `measurement-platform/dbt/` | `dbt parse`, `dbt run`, `dbt test` |
| **Slack bot** | TypeScript | `measurement-platform/services/slack-bot/` | `npm run build` then `npm start` |
| **Prefect** | Python | `measurement-platform/orchestration/prefect/` | `prefect server start` (server), then run flows |
| **Model runner** | Python + R | `measurement-platform/services/model-runner/` | `python src/runner.py` |
| **Metabase dashboards** | Python | `measurement-platform/dashboards/metabase/` | `python create_mvp_dashboards.py` |

### Gotchas

- `$HOME/.local/bin` must be on `PATH` for `dbt`, `prefect`, and other pip-installed CLI tools. This is already configured in `~/.bashrc`.
- dbt profiles live at `measurement-platform/dbt/profiles.yml` (copied from `profiles.yml.template`). They use env vars `SUPABASE_DB_HOST`, `SUPABASE_DB_USER`, `SUPABASE_DB_PASSWORD`. Without these, `dbt parse` works but `dbt run`/`dbt compile` will fail with a connection error — this is expected without Supabase credentials.
- The Slack bot requires `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, and Supabase env vars in a `.env` file (see `measurement-platform/.env.example`).
- Prefect server runs on `http://127.0.0.1:4200`. Set `PREFECT_API_URL=http://127.0.0.1:4200/api` before running flows or deploying.
- There are three separate Python `requirements.txt` files (prefect, model-runner, metabase). The Slack bot uses npm (`package-lock.json`).
- No linter or pre-commit hooks are configured in this repository.
- No automated test suite beyond `dbt test` (which requires a live database).
