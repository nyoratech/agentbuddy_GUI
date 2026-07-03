"""
Mock agent worker.

In the full FinBuddy project a background task hands the prompt to a real
LLM/agent pipeline (see db_light/main.py -> gen_portfolio etc.). Here we keep
the *exact same shape* of that pipeline but replace the agent with a mock so
the whole notification path can be demonstrated without any model/tool running:

    queued -> in_progress (N progress updates) -> completed

At every step we:
  * update the job row in the database,
  * cache the latest status/result in Redis (so /api/jobs/{id} is instant),
  * publish a notification to RabbitMQ so the frontend updates live.

Swap `mock_agent_reply()` for a real agent call and nothing else changes.
"""
import asyncio
import logging

import redis.asyncio as aioredis

from . import db, cache
from .config import get_redis_url, MOCK_JOB_STEPS, MOCK_JOB_STEP_SECONDS
from .messaging import Token, publish_progress, publish_completion

logger = logging.getLogger("finbuddy.worker")


def mock_agent_reply(prompt: str) -> str:
    """Produce a deterministic, obviously-fake 'agent' answer."""
    prompt = (prompt or "").strip()
    return (
        f"**(mock agent)** I received your request:\n\n> {prompt}\n\n"
        "In the full system this is where a real agent would run tools, query "
        "the database and return an analysis. For this minimal interface I am a "
        "stub that simply confirms the round-trip through the backend, the "
        "background job queue and the RabbitMQ notification bus all work."
    )


async def _cache_job(redis, job_id: str, status: str, result: str = "", chat_id: str = "") -> None:
    try:
        await redis.set(
            cache.job_key(job_id),
            cache.payload(status, result, chat_id),
            ex=cache.TTL_SECONDS,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Redis cache write failed for %s: %s", job_id, exc)


async def run_job(job_id: str, user_id: str, chat_id: str, prompt: str) -> None:
    """Process one background job end-to-end (called via BackgroundTasks)."""
    token = Token(user_id=user_id, job_id=job_id, chat_id=chat_id)
    redis = aioredis.from_url(get_redis_url(), decode_responses=True)

    try:
        db.update_job(job_id, "in_progress")
        await _cache_job(redis, job_id, "in_progress", chat_id=chat_id)

        for step in range(1, MOCK_JOB_STEPS + 1):
            await asyncio.sleep(MOCK_JOB_STEP_SECONDS)
            text = f"Working... step {step}/{MOCK_JOB_STEPS}"
            await publish_progress(token, text)
            await _cache_job(redis, job_id, "in_progress", text, chat_id)

        answer = mock_agent_reply(prompt)
        db.update_job(job_id, "completed", result=answer)
        db.add_message(user_id, chat_id, "assistant", answer)
        await _cache_job(redis, job_id, "completed", answer, chat_id)
        await publish_completion(token, answer)
        logger.info("Job %s completed", job_id)

    except Exception as exc:  # pragma: no cover
        logger.exception("Job %s failed", job_id)
        db.update_job(job_id, "failed", result=str(exc))
        await _cache_job(redis, job_id, "failed", str(exc), chat_id)
        await publish_completion(token, f"Job failed: {exc}")
    finally:
        await redis.aclose()
