"""
Redis job-state cache.

The worker writes the latest job status/result here (see worker.py); the API
reads it as a fast path in GET /api/jobs/{job_id}, falling back to the database
when Redis is unavailable or the entry has expired. This keeps a single source
of truth for the cache key format and payload shape.
"""
import json
import logging
from typing import Optional, Dict, Any

import redis

from .config import get_redis_url

logger = logging.getLogger("finbuddy.cache")

TTL_SECONDS = 3600


def job_key(job_id: str) -> str:
    return f"job:{job_id}"


def payload(status: str, result: str = "", chat_id: str = "") -> str:
    return json.dumps({"status": status, "result": result, "chat_id": chat_id})


def read_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Return the cached {status, result, chat_id} for a job, or None."""
    try:
        client = redis.from_url(get_redis_url(), decode_responses=True)
        raw = client.get(job_key(job_id))
        client.close()
        return json.loads(raw) if raw else None
    except Exception as exc:  # Redis down / unreachable -> caller falls back to DB
        logger.warning("Redis read failed for %s: %s", job_id, exc)
        return None
