"""
Live RabbitMQ round-trip test.

Publishes a notification through the backend helper and consumes it the same
way the frontend does, asserting the payload survives the trip intact.

Skipped automatically when no broker is reachable (e.g. bare `pytest` with no
RabbitMQ), so it is a no-op locally but a real integration check in
docker-compose / CI.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest  # noqa: E402
import aio_pika  # noqa: E402

from app.config import get_rabbitmq_url, JOBS_EXCHANGE  # noqa: E402
from app.messaging import Token, publish_completion  # noqa: E402


async def _broker_available() -> bool:
    try:
        conn = await asyncio.wait_for(aio_pika.connect_robust(get_rabbitmq_url()), timeout=3)
        await conn.close()
        return True
    except Exception:
        return False


@pytest.mark.asyncio
async def test_publish_is_received_by_consumer():
    if not await _broker_available():
        pytest.skip("no RabbitMQ broker reachable")

    user_id, job_id = "demo", "roundtrip-job"
    routing_key = f"user.{user_id}.job.*"

    conn = await aio_pika.connect_robust(get_rabbitmq_url())
    channel = await conn.channel()
    exchange = await channel.declare_exchange(JOBS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
    queue = await channel.declare_queue("", exclusive=True)
    await queue.bind(exchange, routing_key)

    # publish AFTER the consumer queue is bound
    await publish_completion(Token(user_id=user_id, job_id=job_id, chat_id="default"), "hello world")

    incoming = await asyncio.wait_for(queue.get(timeout=5), timeout=6)
    payload = json.loads(incoming.body.decode())
    await incoming.ack()
    await conn.close()

    assert payload["user_id"] == user_id
    assert payload["job_id"] == job_id
    assert payload["status"] == "completed"
    assert payload["result"] == "hello world"
