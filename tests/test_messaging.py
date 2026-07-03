"""Unit tests for the RabbitMQ message contract (no broker needed)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.messaging import Token, Message  # noqa: E402


def test_routing_key():
    token = Token(user_id="demo", job_id="abc123", chat_id="default")
    assert token.routing_key() == "user.demo.job.abc123"


def test_token_as_dict():
    token = Token(user_id="demo", job_id="abc123", chat_id="default")
    assert token.as_dict() == {"user_id": "demo", "job_id": "abc123", "chat_id": "default"}


def test_message_merges_token_fields():
    token = Token(user_id="demo", job_id="abc123", chat_id="default")
    msg = Message(result="done", status="completed", message_type="job_update")
    payload = msg.merge_token(token).as_dict()
    assert payload["result"] == "done"
    assert payload["status"] == "completed"
    assert payload["message_type"] == "job_update"
    # token identifiers must ride along so the frontend can route the update
    assert payload["user_id"] == "demo"
    assert payload["job_id"] == "abc123"
    assert payload["chat_id"] == "default"


def test_message_extra_fields():
    msg = Message(result="x", extra_field="hello")
    assert msg.as_dict()["extra_field"] == "hello"
