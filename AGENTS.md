# AGENTS.md

## Cursor Cloud specific instructions

### Repo layout

Everything lives under `measurement-platform/`. See `measurement-platform/README.md` for the full structure and local dev commands.

### Architecture: shared-DB multi-tenant

All clients share **one Supabase project**. Data is separated by a `client_slug` column on every table. Key env var: `CLIENT_SLUG` (used by Slack bot, model runner, Prefect flows).

- **Shared platforms** (Meta, Google, TikTok): one Airbyte connection per platform, all clients mixed. dbt joins to `client_ad_accounts` seed to derive `client_slug` from ad account IDs.
- **Per-client platforms** (Shopify, Klaviyo): separate Airbyte connection per client. Table names are prefixed: `{client_slug}_orders`, `{client_slug}_klaviyo_campaigns`.
- **dbt run per client**: `dbt run --vars '{client_slug: expand}'`
- **Provisioning a new client**: `python ops/client-provision/provision_client.py <slug> --supabase-url ... --supabase-key ...`

### Services overview

| Service | Language | Location | Quick command |
|---------|----------|----------|---------------|
| **dbt** | SQL | `measurement-platform/dbt/` | `cd measurement-platform/dbt && dbt parse --profiles-dir .` |
| **Slack bot** | TypeScript | `measurement-platform/services/slack-bot/` | `cd measurement-platform/services/slack-bot && npm run build` |
| **Model runner** | Python + R | `measurement-platform/services/model-runner/` | `pip install -r measurement-platform/services/model-runner/requirements.txt` |
| **Prefect orchestration** | Python | `measurement-platform/orchestration/prefect/` | `prefect server start` (port 4200) |
| **Metabase dashboards** | Python | `measurement-platform/dashboards/metabase/` | Scripts create cards via Metabase API |

### Non-obvious gotchas

- **PATH**: `dbt` and `prefect` CLIs install to `~/.local/bin`. Already added to `~/.bashrc` by the update script.
- **dbt profiles**: The update script copies `profiles.yml.template` to `profiles.yml`. Without `SUPABASE_DB_PASSWORD`, `dbt compile`/`dbt run` fail at connection, but `dbt parse --profiles-dir .` succeeds for structural validation.
- **DB password auth**: The direct PostgreSQL connection (dbt, psql) uses `SUPABASE_DB_HOST`/`SUPABASE_DB_USER`/`SUPABASE_DB_PASSWORD`. The Supabase REST API uses `SUPABASE_URL`/`SUPABASE_SERVICE_KEY`. If dbt can't connect, verify the password doesn't have special characters that need escaping, and that the user format is `postgres.<project_ref>`.
- **Slack bot**: Uses `npm` (has `package-lock.json`). Build: `npm run build`. Dev: `npm run dev`. Requires `CLIENT_SLUG`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, and Supabase env vars. Each client runs its own bot process.
- **Metabase dashboard scripts**: Accept `--client <slug>` and `--database-name <name>` flags for multi-client. KPI number cards use `smartscalar` (Trend) display with `compare_mode` filter (`previous_period` or `previous_year`). The "vs. previous day" label in Metabase is cosmetic — the values represent full-period aggregates.
- **Prefect**: Start with `prefect server start --host 0.0.0.0 --port 4200`. Per-client deployments use `CLIENT_SLUG=<slug> bash deploy.sh`.
- **No lockfile for Python**: Python requirements use `>=` version specs.
- **No linter config**: No ESLint/Prettier for Slack bot, no Python linter. TypeScript strict mode enabled.
- **User runs Windows/PowerShell**: All documentation and setup commands should use PowerShell syntax (`$env:VAR = "value"`) not bash (`export VAR=value`).

### Lint / Build / Test

- **Slack bot lint**: `cd measurement-platform/services/slack-bot && npx tsc --noEmit`
- **Slack bot build**: `cd measurement-platform/services/slack-bot && npm run build`
- **dbt parse (structural)**: `cd measurement-platform/dbt && dbt parse --profiles-dir .`
- **dbt test (needs DB)**: `cd measurement-platform/dbt && dbt test --profiles-dir .`
- **Prefect health**: `curl -s http://127.0.0.1:4200/api/health`
- **Supabase REST API test**: `python3 -c "from supabase import create_client; import os; c = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY']); print(c.table('client_config').select('*').execute().data)"`
