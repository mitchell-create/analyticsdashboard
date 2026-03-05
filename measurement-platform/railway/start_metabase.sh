#!/usr/bin/env bash
set -euo pipefail

PORT_VALUE="${PORT:-3000}"
export MB_JETTY_PORT="${MB_JETTY_PORT:-$PORT_VALUE}"

echo "Starting Metabase on port ${MB_JETTY_PORT}"
exec java -jar /app/metabase.jar
