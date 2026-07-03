"""
RabbitMQ (AMQP) notification helpers.

This is a trimmed-down version of the full project's
`db_light/message_queue/message_faststream.py`. It keeps the exact same wire
contract so the frontend consumer (and the real FinBuddy backend) understand
each other:

  * Exchange : "jobs_exchange"  (topic, durable)
  * Routing  : "user.{user_id}.job.{job_id}"
  * Payload  : JSON dict with at least
               {user_id, chat_id, job_id, message_type, status, result}

`Token` carries the identifiers, `Message` carries the payload. Publishing is
done with aio_pika (async) which is already a dependency of the main project.
"""
import json
import logging
from typing import Dict, Any

import aio_pika

from .config import get_rabbitmq_url, JOBS_EXCHANGE

logger = logging.getLogger("finbuddy.messaging")


class Token:
    """Identifiers used to build the routing key."""

    def __init__(self, user_id: str, job_id: str, chat_id: str = ""):
        self.user_id = user_id
        self.job_id = job_id
        self.chat_id = chat_id

    def routing_key(self) -> str:
        return f"user.{self.user_id}.job.{self.job_id}"

    def as_dict(self) -> Dict[str, Any]:
        return {"user_id": self.user_id, "job_id": self.job_id, "chat_id": self.chat_id}


class Message:
    """The notification payload sent to the frontend."""

    def __init__(
        self,
        result: str = "",
        status: str = "in_progress",
        message_type: str = "job_update",
        **extra: Any,
    ):
        self.data: Dict[str, Any] = {
            "result": result,
            "status": status,
            "message_type": message_type,
        }
        self.data.update(extra)

    def merge_token(self, token: Token) -> "Message":
        self.data.update(token.as_dict())
        return self

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.data)


async def publish_notification(token: Token, message: Message) -> bool:
    """
    Publish a single notification to the jobs exchange.

    A fresh connection is opened per publish. That is perfectly fine for the low
    volume of a demo and keeps the code simple / stateless (works the same with
    CloudAMQP where long-lived connections need extra care).
    """
    routing_key = token.routing_key()
    body = json.dumps(message.merge_token(token).as_dict()).encode()

    try:
        connection = await aio_pika.connect_robust(get_rabbitmq_url())
        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                JOBS_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
            )
            await exchange.publish(
                aio_pika.Message(body=body, content_type="application/json"),
                routing_key=routing_key,
            )
        logger.info("Published notification -> %s : %s", routing_key, message.data.get("status"))
        return True
    except Exception as exc:  # pragma: no cover - network failures
        logger.error("Failed to publish notification (%s): %s", routing_key, exc)
        return False


async def publish_progress(token: Token, text: str) -> bool:
    return await publish_notification(
        token, Message(result=text, status="in_progress", message_type="job_update")
    )


async def publish_completion(token: Token, text: str) -> bool:
    return await publish_notification(
        token, Message(result=text, status="completed", message_type="job_update")
    )
