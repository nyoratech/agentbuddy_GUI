#!/usr/bin/env bash
#
# One-command local setup — NO Docker, NO RabbitMQ/Redis/Postgres.
#
# The backend and the frontend are separate apps with different (and partly
# conflicting) dependency pins, so each gets its OWN virtualenv. Both are
# started in SYNCHRONOUS mode (chat answers come back inline; no message broker
# needed) against a local SQLite database.
#
# When it's up: open http://localhost:3003 and log in with a seeded account:
#   demo1@demo.com / demo1   ·   demo2@demo2.com / demo2   ·   demo3@demo.com / demo3
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PY="${PYTHON:-python3}"
BE_VENV="$HERE/.venv-backend"
FE_VENV="$HERE/.venv-frontend"

echo "==> [1/4] Installing the backend (its own virtualenv)"
"$PY" -m venv "$BE_VENV"
"$BE_VENV/bin/pip" install --quiet --upgrade pip
"$BE_VENV/bin/pip" install --quiet -r backend/requirements.txt

echo "==> [2/4] Installing the frontend (its own virtualenv) — this is the big one"
"$PY" -m venv "$FE_VENV"
"$FE_VENV/bin/pip" install --quiet --upgrade pip
"$FE_VENV/bin/pip" install --quiet -r frontend/requirements.txt

# Shared JWT secret so the backend accepts the frontend's tokens; sync mode.
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-dev-secret-change-me}"
export USE_ASYNC_JOBS="false"
export BACKEND_URL="http://localhost:8008"

echo "==> [3/4] Starting the FastAPI backend on :8008"
( cd "$HERE/backend" && "$BE_VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8008 \
    >/tmp/finbuddy_backend.log 2>&1 ) &
BACKEND_PID=$!

echo "==> [4/4] Preparing the chat DB (migrate + seed) and starting the UI on :3003"
cd "$HERE/frontend"
[ -d alembic ] || "$FE_VENV/bin/reflex" db init >/dev/null
"$FE_VENV/bin/reflex" db makemigrations >/dev/null 2>&1 || true
"$FE_VENV/bin/reflex" db migrate >/dev/null
"$FE_VENV/bin/python" seed_demo.py || true

trap 'echo; echo "Stopping..."; kill $BACKEND_PID ${FRONTEND_PID:-} 2>/dev/null || true' INT TERM EXIT
"$FE_VENV/bin/reflex" run --frontend-port 3003 --backend-port 8003 &
FRONTEND_PID=$!

echo ""
echo "======================================================================"
echo "  FinBuddy is starting up (first run compiles the UI — give it a minute)."
echo "  UI:      http://localhost:3003     (login: demo1@demo.com / demo1)"
echo "           other accounts: demo2@demo2.com / demo2 · demo3@demo.com / demo3"
echo "  Backend: http://localhost:8008/health   (log: /tmp/finbuddy_backend.log)"
echo "  Press Ctrl+C to stop."
echo "======================================================================"
wait $FRONTEND_PID
