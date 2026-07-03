#!/bin/sh
# Migrate the chat-history DB, seed the demo user, then start Reflex.
set -e

# Apply migrations (generate them first if the DB is brand new / models changed).
reflex db migrate 2>/dev/null || (reflex db makemigrations && reflex db migrate)

# Seed demo / demo (no-op if it already exists).
python seed_demo.py || true

exec reflex run --env prod --frontend-port 3003 --backend-port 8003
