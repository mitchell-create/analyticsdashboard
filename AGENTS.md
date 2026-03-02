# AGENTS.md

## Cursor Cloud specific instructions

### Repo layout

Everything lives under `measurement-platform/`. See `measurement-platform/README.md` for the full structure and local dev commands.

### Services overview

| Service | Language | Location | Quick command |
|---------|----------|----------|---------------|
| **dbt** | SQL | `measurement-platform/dbt/` | `cd measurement-platform/dbt && dbt parse --profiles-dir .` |
| **Slack bot** | TypeScript | `measurement-platform/services/slack-bot/` | `cd measurement-platform/services/slack-bot && npm run build` |
| **Model runner** | Python + R | `measurement-platform/services/model-runner/` | `pip install -r measurement-platform/services/model-runner/requirements.txt` |
| **Prefect orchestration** | Python | `measurement-platform/orchestration/prefect/` | `prefect server start` (port 4200) |
| **Metabase dashboards** | Python | `measurement-platform/dashboards/metabase/` | Script only; needs Metabase instance |

### Non-obvious gotchas

- **PATH**: `dbt` and `prefect` CLIs install to `~/.local/bin`. This is already added to `~/.bashrc` by the environment setup. If running in a fresh shell, ensure `export PATH="$HOME/.local/bin:$PATH"` is active.
- **dbt profiles**: The update script copies `profiles.yml.template` to `profiles.yml` in the dbt directory. Without Supabase credentials (`SUPABASE_DB_PASSWORD` etc.), `dbt compile` and `dbt run` will fail at the connection step, but `dbt parse --profiles-dir .` will succeed and is sufficient to validate model/test structure.
- **Slack bot**: Uses `npm` (has `package-lock.json`). Build with `npm run build` (TypeScript). Dev mode: `npm run dev` (uses `ts-node`). Requires `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, and Supabase env vars to actually start.
- **Prefect server**: Start with `prefect server start --host 0.0.0.0 --port 4200`. Set `PREFECT_API_URL=http://127.0.0.1:4200/api` before running flows or deploying. The daily pipeline flow (`orchestration/prefect/flows/daily_pipeline.py`) needs dbt on PATH and Supabase credentials.
- **All services depend on Supabase**: Without `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and `SUPABASE_DB_*` credentials, services can be built/compiled but not run end-to-end against real data.
- **No lockfile for Python**: Python requirements use `>=` version specs. Pin versions if reproducibility issues arise.
- **No linter config**: There is no ESLint or Prettier config for the Slack bot, and no Python linter config (e.g. ruff, flake8). TypeScript strict mode is enabled via `tsconfig.json`.

### Lint / Build / Test

- **Slack bot lint**: `cd measurement-platform/services/slack-bot && npx tsc --noEmit` (type-check without emitting)
- **Slack bot build**: `cd measurement-platform/services/slack-bot && npm run build`
- **dbt parse (structural check)**: `cd measurement-platform/dbt && dbt parse --profiles-dir .`
- **dbt test (needs DB)**: `cd measurement-platform/dbt && dbt test --profiles-dir .`
- **Prefect health**: `curl -s http://127.0.0.1:4200/api/health` (after starting server)
