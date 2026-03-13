#!/usr/bin/env bash
# deploy.sh — Register Prefect flows and create deployments.
# Supports per-client deployments when CLIENT_SLUG is set.
#
# Usage:
#   ./deploy.sh                         # default deployments (no client prefix)
#   CLIENT_SLUG=acme ./deploy.sh        # client-specific: acme-daily, acme-experiments, acme-qa
#
# Prerequisites: prefect installed, PREFECT_API_URL set (or local server on 4200).
# Per-client: set SUPABASE_URL, SUPABASE_SERVICE_KEY, SLACK_* for the client first.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOWS_DIR="$(cd "$SCRIPT_DIR/../flows" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

export PREFECT_API_URL="${PREFECT_API_URL:-http://127.0.0.1:4200/api}"

CLIENT="${CLIENT_SLUG:-}"
PREFIX=""
if [ -n "$CLIENT" ]; then
  PREFIX="${CLIENT}-"
  echo "==> Deploying for client: $CLIENT"
else
  echo "==> Deploying default (no client prefix)"
fi

echo "==> Deploying Prefect flows from $FLOWS_DIR"

# daily_pipeline
prefect deployment build "$FLOWS_DIR/daily_pipeline.py:daily_pipeline" \
  --name "${PREFIX}daily" \
  --cron "0 6 * * *" \
  --output "$SCRIPT_DIR/${PREFIX}daily_pipeline-deployment.yaml" \
  --path "$REPO_ROOT" \
  || true

# run_experiments
prefect deployment build "$FLOWS_DIR/run_experiments.py:run_experiments" \
  --name "${PREFIX}scheduled" \
  --cron "0 */6 * * *" \
  --output "$SCRIPT_DIR/${PREFIX}run_experiments-deployment.yaml" \
  --path "$REPO_ROOT" \
  || true

# qa_checks
prefect deployment build "$FLOWS_DIR/qa_checks.py:qa_checks" \
  --name "${PREFIX}qa_checks" \
  --output "$SCRIPT_DIR/${PREFIX}qa_checks-deployment.yaml" \
  --path "$REPO_ROOT" \
  || true

echo ""
echo "==> Apply deployments:"
echo "    prefect deployment apply $SCRIPT_DIR/${PREFIX}*.yaml"
echo ""
echo "==> Start worker:"
echo "    prefect worker start --pool default-pool"
if [ -n "$CLIENT" ]; then
  echo ""
  echo "==> Client '$CLIENT' env vars must be set in the worker process:"
  echo "    SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_DB_URL"
  echo "    SLACK_BOT_TOKEN, SLACK_ALERT_CHANNEL_ID"
fi
