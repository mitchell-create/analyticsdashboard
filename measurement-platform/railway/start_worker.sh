#!/usr/bin/env bash
set -euo pipefail

if [ ! -f /app/dbt/profiles.yml ] && [ -f /app/dbt/profiles.yml.template ]; then
  cp /app/dbt/profiles.yml.template /app/dbt/profiles.yml
fi

export DBT_PROJECT_DIR="${DBT_PROJECT_DIR:-/app/dbt}"
export DBT_PROFILES_DIR="${DBT_PROFILES_DIR:-/app/dbt}"
export PREFECT_WORK_POOL="${PREFECT_WORK_POOL:-default-agent-pool}"

echo "Starting Prefect worker in pool: ${PREFECT_WORK_POOL}"
exec prefect worker start --pool "${PREFECT_WORK_POOL}" --type process
