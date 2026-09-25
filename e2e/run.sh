#!/usr/bin/env bash
# End-to-end test: the real app code drives the real server, database, Redis
# and background worker over HTTP, with a fake Telegram (e2e/fake_telegram.py).
#
# Needs PostgreSQL and Redis running, the backend virtualenv (backend/.venv)
# and Flutter. Uses a database ending in _e2e, which it wipes:
#
#   FF_E2E_DATABASE_URL=postgresql+asyncpg://user:password@127.0.0.1:5432/ff_e2e e2e/run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/e2e/.run"
PY="${PYTHON:-$ROOT/backend/.venv/bin/python}"
mkdir -p "$RUN"

export FF_ENV=dev
export FF_DATABASE_URL="${FF_E2E_DATABASE_URL:-postgresql+asyncpg://postgres@127.0.0.1:5432/ff_e2e}"
export FF_REDIS_URL="${FF_E2E_REDIS_URL:-redis://127.0.0.1:6379/13}"
export FF_PUBLIC_BASE_URL="http://127.0.0.1:8000"
export FF_TELEGRAM_API_BASE="http://127.0.0.1:8081"
export FF_LOG_LEVEL=WARNING
export PYTHONPATH="$ROOT/backend:$ROOT/e2e"

pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT

wait_for() {
  for _ in $(seq 1 60); do
    if curl -fsS "$1" >/dev/null 2>&1; then return 0; fi
    sleep 0.5
  done
  echo "Timed out waiting for $1" >&2
  exit 1
}

echo "== Fresh database and Redis"
"$PY" "$ROOT/e2e/stack.py" reset
"$PY" - <<'PYEOF'
import os, redis
redis.Redis.from_url(os.environ["FF_REDIS_URL"]).flushdb()
PYEOF

echo "== Starting fake Telegram, API and worker"
(cd "$ROOT/e2e" && exec "$PY" -m uvicorn fake_telegram:app --host 127.0.0.1 --port 8081 --log-level warning) >"$RUN/telegram.log" 2>&1 &
pids+=($!)
(cd "$ROOT/backend" && exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning) >"$RUN/api.log" 2>&1 &
pids+=($!)
wait_for http://127.0.0.1:8081/control/health
wait_for http://127.0.0.1:8000/readyz
(cd "$ROOT/backend" && exec "$PY" -m app.cli worker) >"$RUN/worker.log" 2>&1 &
pids+=($!)

echo "== Bots, channels, funded pool and an admin"
"$PY" "$ROOT/e2e/stack.py" setup

echo "== App against the running stack"
cd "$ROOT/mobile"
E2E_API="http://127.0.0.1:8000" \
E2E_TELEGRAM="http://127.0.0.1:8081" \
E2E_STACK="$PY $ROOT/e2e/stack.py" \
E2E_RUN_DIR="$RUN" \
  flutter test test_e2e --reporter expanded
