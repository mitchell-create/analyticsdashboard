#!/usr/bin/env bash
# provision_client.sh — Create a new client measurement environment (Pattern B: 1 DB per client)
# Usage: ./provision_client.sh <client_slug>
# Prerequisites: Supabase CLI, env vars for SUPABASE_ACCESS_TOKEN (or login via supabase login)

set -euo pipefail

CLIENT_SLUG="${1:?Usage: $0 <client_slug>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "==> Provisioning client: $CLIENT_SLUG"

# 1. Supabase project (create via dashboard or CLI)
#    https://supabase.com/dashboard — New Project, name e.g. "measurement-${CLIENT_SLUG}"
#    Or: supabase projects create "measurement-${CLIENT_SLUG}" --org-id <org_id>
echo "==> Step 1: Create Supabase project"
echo "    Create project in Supabase dashboard: https://supabase.com/dashboard"
echo "    Suggested name: measurement-${CLIENT_SLUG}"
echo "    After creation, set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env for this client."

# 2. Run warehouse schema migrations
echo "==> Step 2: Apply warehouse schema"
if [ -d "$REPO_ROOT/warehouse/schema" ]; then
  for f in "$REPO_ROOT/warehouse/schema"/*.sql; do
    [ -f "$f" ] && echo "    Run migration: $f (via Supabase SQL Editor or psql)"
  done
  echo "    Execute each 000_core.sql .. 050_quality.sql in order against the new project."
else
  echo "    Skipped: warehouse/schema not found"
fi

# 3. Seed dim_geo if present
echo "==> Step 3: Seed dim_geo (if applicable)"
if [ -f "$REPO_ROOT/warehouse/seeds/dim_geo_states.csv" ]; then
  echo "    Load warehouse/seeds/dim_geo_states.csv into dim_geo (or run dbt seed after dbt setup)."
else
  echo "    Skipped: warehouse/seeds/dim_geo_states.csv not found"
fi

# 4. Airbyte workspace
echo "==> Step 4: Airbyte connections"
echo "    In Airbyte: create/duplicate workspace for $CLIENT_SLUG."
echo "    Add sources: Meta Ads, Google Ads, TikTok Ads, Shopify, Klaviyo."
echo "    Set destination: Supabase (this project's connection string)."
echo "    Schedule: daily sync; backfill 90 days then expand to 12–24 months."

# 5. Metricool
echo "==> Step 5: Metricool"
echo "    Connect TikTok account for $CLIENT_SLUG."
echo "    Configure daily export or API sync into Supabase (fact_tiktok_organic_daily or raw staging table)."

# 6. Metabase
echo "==> Step 6: Metabase"
echo "    Add Supabase database connection (this project) in Metabase."
echo "    Clone MVP dashboards from template; point to this client's DB."
echo "    Use only marts (dbt output) for reporting."

# 7. Slack
echo "==> Step 7: Slack"
echo "    Create channel for $CLIENT_SLUG (e.g. #measurement-${CLIENT_SLUG})."
echo "    Invite Slack bot; configure alerts and Q&A for this client's warehouse."

# 8. Prefect
echo "==> Step 8: Prefect"
echo "    Register deployment for this client (daily_pipeline, run_experiments, qa_checks)."
echo "    Set client-specific env (SUPABASE_URL, SUPABASE_SERVICE_KEY, AIRBYTE_API_KEY, etc.)."

echo ""
echo "==> Next: Complete onboarding_checklist.md for $CLIENT_SLUG"
