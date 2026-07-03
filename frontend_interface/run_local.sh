#!/usr/bin/env bash
#
# Run the whole stack locally WITHOUT docker.
#
# Requirements on your machine:
#   * a running RabbitMQ  (amqp://guest:guest@localhost/)   -> live notifications
#   * a running Redis      (redis://localhost:6379)          -> optional cache
#   * (optional) Postgres with the RBAC schema               -> chat sharing
#   * Python 3.11+ with both requirements.txt installed
#
# Chat history lives in a local SQLite file (frontend/reflex.db) — no Postgres
# needed for the core app. The backend agent is a mock.
#
# Quickest way to get the brokers locally is docker:
#   docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3.13-management
#   docker run -d --name redis -p 6379:6379 redis:7-alpine
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$HERE/.env" ]; then
  set -a; . "$HERE/.env"; set +a
fi
# The frontend mints JWTs the backend must accept -> share the secret.
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-dev-secret-change-me}"

echo "==> Starting FastAPI backend on :8008"
( cd "$HERE/backend" && uvicorn app.main:app --host 0.0.0.0 --port 8008 ) &
BACKEND_PID=$!

echo "==> Preparing frontend DB (migrate + seed demo user)"
cd "$HERE/frontend"
[ -d alembic ] || reflex db init
reflex db makemigrations >/dev/null 2>&1 || true
reflex db migrate
python seed_demo.py || true

echo "==> Starting Reflex frontend on :3000 (state backend :8000)"
reflex run --frontend-port 3000 --backend-port 8000 &
FRONTEND_PID=$!

trap 'echo "Stopping..."; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true' INT TERM EXIT

echo ""
echo "Backend : http://localhost:8008/health"
echo "Frontend: http://localhost:3000   (login: demo / demo)"
echo "Press Ctrl+C to stop."
wait
