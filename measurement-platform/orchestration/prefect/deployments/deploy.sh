#!/usr/bin/env bash
# deploy.sh — Register Prefect flows and create deployments (e.g. daily schedule).
# Prerequisites: prefect installed, PREFECT_API_URL set (or use local Prefect server).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOWS_DIR="$(cd "$SCRIPT_DIR/../flows" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

export PREFECT_API_URL="${PREFECT_API_URL:-http://127.0.0.1:4200/api}"

echo "==> Deploying Prefect flows from $FLOWS_DIR"

# Ensure prefect project is set (optional)
# prefect config set PREFECT_API_URL="$PREFECT_API_URL"

# Build deployment: daily_pipeline (daily schedule)
prefect deployment build "$FLOWS_DIR/daily_pipeline.py:daily_pipeline" \
  --name "daily" \
  --cron "0 6 * * *" \
  --output "$SCRIPT_DIR/daily_pipeline-deployment.yaml" \
  --path "$REPO_ROOT" \
  || true

# Build deployment: run_experiments (e.g. every 6h for queued experiments)
prefect deployment build "$FLOWS_DIR/run_experiments.py:run_experiments" \
  --name "scheduled" \
  --cron "0 */6 * * *" \
  --output "$SCRIPT_DIR/run_experiments-deployment.yaml" \
  --path "$REPO_ROOT" \
  || true

# Build deployment: qa_checks (on demand or chained after daily_pipeline)
prefect deployment build "$FLOWS_DIR/qa_checks.py:qa_checks" \
  --name "qa_checks" \
  --output "$SCRIPT_DIR/qa_checks-deployment.yaml" \
  --path "$REPO_ROOT" \
  || true

echo "==> Apply deployments with: prefect deployment apply $SCRIPT_DIR/*.yaml"
echo "==> Start worker: prefect worker start --pool default-pool"
