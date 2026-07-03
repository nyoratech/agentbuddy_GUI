"""Tests for the Redis job-state cache helpers."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import cache  # noqa: E402


def test_job_key():
    assert cache.job_key("abc") == "job:abc"


def test_payload_shape():
    data = json.loads(cache.payload("completed", "answer", "default"))
    assert data == {"status": "completed", "result": "answer", "chat_id": "default"}


def test_read_job_returns_none_without_redis(monkeypatch):
    # Point at a port with nothing listening -> read must degrade to None.
    monkeypatch.setenv("REDIS_URL", "redis://localhost:1/0")
    assert cache.read_job("missing") is None
