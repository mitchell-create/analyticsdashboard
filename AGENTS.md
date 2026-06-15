# AGENTS.md — Analytics Dashboard

> Read this file first when you start work on this repo. It explains what the project is, where things live, the rules you must not break, and how to verify your changes.

## Who works on this codebase

- **Mitchell Thompson** (owner, [mitchell@nexocore.ca](mailto:mitchell@nexocore.ca)) — runs Nexocore, a multi-client marketing analytics agency. Bi-monthly client reports.
- **Claude Code** runs on Mitchell's work PC. Architect role: writes scripts, runbooks, design decisions, reviews diffs.
- **Codex** runs on the dedicated always-on PC. Executor role: runs migrations, hosts services, applies changes from the repo.
- **Repo is the contract.** No cross-AI chat. If you need design judgment, ask Mitchell — he'll bring it to the architect side and update this repo.

## What the platform does

Multi-client marketing analytics for ~6 ecommerce brands. Pulls ad spend (Meta, Google, TikTok) + Shopify orders + Klaviyo email + GA4 traffic into a Postgres warehouse, transforms with dbt, surfaces in Metabase dashboards, answers Slack questions in natural language, and posts scheduled performance reports.

```
[Ad platforms] [Shopify] [Klaviyo] [GA4]
       │           │         │        │
       ▼           ▼         ▼        ▼
    Airbyte ───────────  klaviyo_sync.py (direct API)
       │                            │
       └──► raw schema ◄────────────┘
                │
                ▼  (dbt run)
          public_marts schema
                │
   ┌────────────┼────────────┬───────────────┐
   ▼            ▼            ▼               ▼
 Metabase   Slack bot   Prefect flows   chubble_report.py
            (NL → SQL)  (scheduled)     (bi-monthly to Slack)
```

## Current migration state (as of 2026-05-05)

We are mid-migration from **Supabase Cloud Postgres** → **local Postgres on a dedicated always-on PC**. See `measurement-platform/migration/MIGRATION_RUNBOOK.md`.

Status:
- Code is decoupled from Supabase JS/Python clients — all DB access is now `pg`/`psycopg2` direct (works against any Postgres).
- Migration scripts (`bootstrap-dedicated-pc.ps1`, `MIGRATION_RUNBOOK.md`, `backup-warehouse.ps1`) are written.
- Region table dropped (1.72 GB reclaimed).
- Meta re-auth is paused for ~1 week (cooldown).
- Dedicated PC bootstrap pending.

## Repo layout

| Path | Purpose |
|---|---|
| `measurement-platform/dbt/` | dbt project (staging + marts) |
| `measurement-platform/dashboards/metabase/` | Metabase SQL + dashboard specs |
| `measurement-platform/services/slack-bot/` | Node.js + TypeScript Slack bot |
| `measurement-platform/services/model-runner/` | Python + R GeoLift / CausalImpact runner (paused — see project memory) |
| `measurement-platform/orchestration/prefect/` | Prefect 3 flows + deployments |
| `measurement-platform/INSIGHTS_PLAYBOOK.md` | **Performance-diagnosis skill** — read this when asked to "analyze <client>"; comparison SQL + signal→cause ruleset + root-cause drill-down + "is it us or the market?" external check, for week-over-week / 30-day insights |
| `measurement-platform/insights/clients/` | **Per-client report memory** — standing context + focus threads + dated report log. Read a client's `<slug>.md` before writing their report, append after (playbook §7) |
| `measurement-platform/orchestration/chubble_report.py` | Bi-monthly Chubble Gum performance report → Slack |
| `measurement-platform/orchestration/klaviyo_sync.py` | Direct Klaviyo API → Postgres sync |
| `measurement-platform/warehouse/schema/` | Postgres DDL |
| `measurement-platform/migration/` | Migration assets (bootstrap, runbook, backup) |
| `measurement-platform/scripts/` | One-off utility scripts |
| `measurement-platform/ops/` | Client provisioning + sync scripts |

## Tech stack

- **Database**: PostgreSQL 16
- **Orchestration**: Prefect 3
- **Transforms**: dbt-postgres
- **Backend**: Node.js 20 + TypeScript (slack-bot), Python 3.12 + R 4.5 (model-runner)
- **BI**: Metabase 0.51 (Java JAR, Temurin 21 JRE)
- **Networking**: Tailscale private mesh between work PC and dedicated PC
- **Backups**: rclone → Google Drive (use `crypt` remote — encrypted)
- **Ingestion**: Airbyte OSS (kind cluster via abctl) + direct Klaviyo Python sync

## Multi-client setup

Client slugs (lowercase, snake_case): `expand`, `chubble`, `babybay`, `crazy_rumors`, `zoka`, `secondkind`. See [client_ad_accounts.csv](measurement-platform/dbt/seeds/client_ad_accounts.csv) for ad account ID mappings.

Every fact/dim table has a `client_slug` column. **Always filter on it.** No queries that scan across clients without explicit intent.

## Conventions

### Coding style

- **TypeScript**: explicit types on exported functions; no `any` (use `unknown` and narrow); prefer `interface` for object shapes; immutable updates with spread.
- **Python**: PEP 8, type hints; prefer `psycopg2.extras.RealDictCursor` for SELECT results; use `with` blocks for connections.
- **SQL**: lowercase keywords; `snake_case` names; schema-qualified refs in dbt models (`{{ source('raw_chubble', 'chubble_orders') }}` / `{{ ref('fact_kpi_daily') }}`); always parameterise — never f-string user input into SQL.
- **Files**: small + focused. 200–400 lines typical, 800 max. Extract utilities when a file gets crowded.
- **Immutability**: never mutate inputs; return new objects.
- **Comments**: write WHY, not WHAT. Skip if removal wouldn't confuse a reader. No multi-paragraph docstrings.

### Database

- `raw` schema → Airbyte landing tables (read-only from app code; only Airbyte writes here).
- `public_marts` schema → dbt-built fact/dim tables.
- `public` schema → application tables (experiments, audit, pipeline_runs, data_quality_flags).
- Connection string: env var `SUPABASE_DB_URL` (kept name during migration; will rename to `DB_URL` post-cutover).

### Multi-tenancy

- Per-client DB connection routed via `services/slack-bot/clients.json` (gitignored — never commit).
- Single warehouse, multi-client filtering via `client_slug` column. Don't split into per-client databases.

## Hard rules — never violate

1. **Never commit secrets.** `.env`, `clients.json`, `*.key`, `airbyte-*-key.json`, `profiles.yml`, OAuth token files. All in `.gitignore`. If you create new config, add to `.gitignore` first.
2. **Never DROP tables/databases without Mitchell's explicit confirmation.** Same for `TRUNCATE` and unbounded `DELETE`. If a migration looks already-applied, STOP and report — don't re-run.
3. **Never `git push --force`** to any branch. Conflicts get resolved, not bulldozed.
4. **Never log secrets.** No `console.log(process.env)`, no `print(db_url)`. Redact in error messages.
5. **No mocks in integration tests.** Real Postgres, real connections. Past incident: mocked tests passed while a real migration was broken.
6. **No `--no-verify`, `--no-gpg-sign`, or auto-accept-all permissions.** If a hook fails, fix the issue.
7. **Stop and ask** if a verification command produces unexpected output, especially during migration phases.

## Verification commands

After any change, run the relevant check:

| What changed | Verify |
|---|---|
| dbt model | `cd measurement-platform/dbt && dbt run --select <model> && dbt test --select <model>` |
| Slack bot TypeScript | `cd measurement-platform/services/slack-bot && npx tsc --noEmit` (must exit 0) |
| Python module | `python -c "from <module> import <symbol>"` (import smoke) |
| DB schema | `psql -d analytics -c "\dt+ <schema>.*"` (compare table sizes before/after) |
| Connection string | `psql "$DB_URL" -c "SELECT 1"` (must return 1) |
| Slack bot logic | `cd measurement-platform/services/slack-bot && npm run dev` (boots without errors) |

## Phase-end protocol (for Codex on the dedicated PC)

After each phase of `MIGRATION_RUNBOOK.md`, output a report to Mitchell:

```
PHASE <n> COMPLETE — <name>

Completed:
- <command/action> → <result>
- <command/action> → <result>

Verifications:
- <check> → PASS/FAIL (<actual output>)

Unexpected:
- <anything that didn't match expectations>

Ready for Phase <n+1>? (y/n)
```

Don't auto-advance. Wait for Mitchell to confirm.

## Escalate to Mitchell when

- A command fails and the error isn't in the runbook.
- A verification returns unexpected output.
- About to do something destructive (DROP, force-push, mass-DELETE, REVOKE).
- A secret-bearing file shows up unexpectedly (e.g., `.env` not gitignored).
- Interactive auth needed (Tailscale login, Postgres password input, Drive OAuth).
- Choosing between two non-trivial paths the runbook doesn't specify.

## Things explicitly OUT of scope right now

- **GeoLift / CausalImpact** — paused. Code stays in repo (`services/model-runner/`) for future re-enable. Don't delete or refactor it.
- **Meta region data** — disabled in Airbyte and dropped from warehouse. Don't re-enable streams or restore data.
- **Supabase Auth / Storage / Edge Functions / Realtime** — never used here. Don't add anything that would.
- **Per-client separate databases** — single warehouse + `client_slug` filtering is the design. Don't propose multi-DB.
