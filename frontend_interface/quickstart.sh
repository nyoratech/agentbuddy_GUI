#!/usr/bin/env bash
#
# One-command local setup — NO Docker, NO RabbitMQ/Redis/Postgres.
#
# Creates a virtualenv, installs the backend + frontend, prepares the chat DB
# (SQLite), seeds a demo user, and starts both servers in SYNCHRONOUS mode
# (chat answers come back inline, so no message broker is needed).
#
# Then open http://localhost:3000 and log in as  demo / demo.
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PY="${PYTHON:-python3}"
VENV="$HERE/.venv"

echo "==> [1/4] Creating virtualenv (.venv) and installing dependencies"
"$PY" -m venv "$VENV"
# shellcheck disable=SC1091
. "$VENV/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt -r frontend/requirements.txt

# Shared JWT secret so the backend accepts the frontend's tokens.
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-dev-secret-change-me}"
# Sync mode: no broker needed.
export USE_ASYNC_JOBS="false"
export BACKEND_URL="http://localhost:8008"

echo "==> [2/4] Starting the FastAPI backend on :8008"
( cd "$HERE/backend" && JWT_SECRET_KEY="$JWT_SECRET_KEY" \
    uvicorn app.main:app --host 0.0.0.0 --port 8008 >/tmp/finbuddy_backend.log 2>&1 ) &
BACKEND_PID=$!

echo "==> [3/4] Preparing the chat database (migrate + seed demo user)"
cd "$HERE/frontend"
[ -d alembic ] || reflex db init >/dev/null
reflex db makemigrations >/dev/null 2>&1 || true
reflex db migrate >/dev/null
python seed_demo.py || true

echo "==> [4/4] Starting the Reflex UI on :3000  (this compiles the frontend once)"
trap 'echo; echo "Stopping..."; kill $BACKEND_PID ${FRONTEND_PID:-} 2>/dev/null || true' INT TERM EXIT
reflex run --frontend-port 3000 --backend-port 8000 &
FRONTEND_PID=$!

echo ""
echo "======================================================================"
echo "  FinBuddy is starting up."
echo "  UI:      http://localhost:3000     (login:  demo / demo)"
echo "  Backend: http://localhost:8008/health"
echo "  Backend log: /tmp/finbuddy_backend.log"
echo "  Press Ctrl+C to stop."
echo "======================================================================"
wait $FRONTEND_PID
