#!/usr/bin/env bash
#
# Run the test suite.
#
# Backend and frontend are separate apps (separate containers/requirements).
# The frontend imports Reflex, which monkeypatches sqlmodel; importing that in
# the same process as the backend's SQLModel tables raises a metaclass
# conflict. So we run the two groups in separate Python processes — which also
# mirrors how they actually run in production.
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "===== backend / messaging / worker / cache ====="
python -m pytest \
  tests/test_backend_api.py \
  tests/test_messaging.py \
  tests/test_worker.py \
  tests/test_cache.py \
  tests/test_rabbitmq_roundtrip.py -q

echo ""
echo "===== frontend shims ====="
python -m pytest tests/test_frontend_shim.py -q

echo ""
echo "===== frontend persistence (reflex models) ====="
python -m pytest tests/test_frontend_persistence.py -q

echo ""
echo "All test groups passed."
