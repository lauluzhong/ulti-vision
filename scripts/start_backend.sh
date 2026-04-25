#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/data/uploads /app/data/transcoded

alembic upgrade head

python -m dramatiq sva.queue --processes "${DRAMATIQ_PROCESSES:-1}" --threads "${DRAMATIQ_THREADS:-4}" &
worker_pid=$!

uvicorn sva.api.app:app --host 0.0.0.0 --port "${PORT:-8000}" &
api_pid=$!

cleanup() {
  kill "$worker_pid" "$api_pid" 2>/dev/null || true
  wait "$worker_pid" "$api_pid" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

wait -n "$worker_pid" "$api_pid"
status=$?
cleanup
exit "$status"
