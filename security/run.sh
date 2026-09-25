#!/usr/bin/env bash
# Security probe: start the real stack (as e2e/run.sh does) and run the probes
# in security/probe.py against it. Uses a database ending in _sec, which it wipes.
#
#   FF_SEC_DATABASE_URL=postgresql+asyncpg://user:password@127.0.0.1:5432/ff_sec security/run.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/security/.run"
PY="${PYTHON:-$ROOT/backend/.venv/bin/python}"
mkdir -p "$RUN"

export FF_ENV=dev
export FF_DATABASE_URL="${FF_SEC_DATABASE_URL:-postgresql+asyncpg://postgres@127.0.0.1:5432/ff_sec}"
export FF_REDIS_URL="${FF_SEC_REDIS_URL:-redis://127.0.0.1:6379/12}"
export FF_PUBLIC_BASE_URL="http://127.0.0.1:8000"
export FF_TELEGRAM_API_BASE="http://127.0.0.1:8081"
export FF_LOG_LEVEL=WARNING
export PYTHONPATH="$ROOT/backend:$ROOT/e2e"

# Reuse the e2e database guard, which refuses anything not ending in _e2e/_sec.
case "${FF_DATABASE_URL%%\?*}" in
  *_sec) ;;
  *) echo "Refusing: FF_SEC_DATABASE_URL must name a database ending in _sec" >&2; exit 1;;
esac

pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT
wait_for() { for _ in $(seq 1 60); do curl -fsS "$1" >/dev/null 2>&1 && return 0; sleep 0.5; done; echo "timeout $1" >&2; exit 1; }

echo "== Fresh database, Redis, bots, channels, funded pool"
SEC_STACK="$ROOT/security/reset.py"
"$PY" "$SEC_STACK" reset
"$PY" - <<PYEOF
import os, redis
redis.Redis.from_url(os.environ["FF_REDIS_URL"]).flushdb()
PYEOF

(cd "$ROOT/e2e" && exec "$PY" -m uvicorn fake_telegram:app --host 127.0.0.1 --port 8081 --log-level warning) >"$RUN/telegram.log" 2>&1 &
pids+=($!)
(cd "$ROOT/backend" && exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning) >"$RUN/api.log" 2>&1 &
pids+=($!)
wait_for http://127.0.0.1:8081/control/health
wait_for http://127.0.0.1:8000/readyz
(cd "$ROOT/backend" && exec "$PY" -m app.cli worker) >"$RUN/worker.log" 2>&1 &
pids+=($!)
"$PY" "$SEC_STACK" setup

echo "== Probing"
"$PY" "$ROOT/security/probe.py"
