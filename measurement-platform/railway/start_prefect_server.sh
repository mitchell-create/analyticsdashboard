#!/usr/bin/env bash
set -euo pipefail

export PREFECT_SERVER_API_HOST="0.0.0.0"
export PREFECT_SERVER_API_PORT="${PORT:-4200}"

# Default to local sqlite if no DB URL is provided.
export PREFECT_API_DATABASE_CONNECTION_URL="${PREFECT_API_DATABASE_CONNECTION_URL:-sqlite+aiosqlite:////app/prefect.db}"

echo "Starting Prefect server on ${PREFECT_SERVER_API_HOST}:${PREFECT_SERVER_API_PORT}"
exec prefect server start --host "${PREFECT_SERVER_API_HOST}" --port "${PREFECT_SERVER_API_PORT}"
