"""End-to-end API tests using FastAPI's TestClient.

RabbitMQ / Redis are not required: the worker degrades gracefully (it logs a
warning if it cannot publish/cache) and the job still completes and persists,
which is exactly what we assert here.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Use a throwaway SQLite DB for the whole test module.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _auth(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "demo"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health(client):
    assert client.get("/health").json()["status"] == "healthy"


def test_login_demo_user(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "demo"})
    assert r.status_code == 200
    assert r.json()["user_id"] == "demo"


def test_login_rejects_bad_password(client):
    r = client.post("/api/auth/login", json={"username": "demo", "password": "nope"})
    assert r.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    h = _auth(client)
    assert client.get("/api/auth/me", headers=h).json()["user_id"] == "demo"


def test_signup_and_duplicate(client):
    r = client.post("/api/auth/signup", json={"username": "newuser", "password": "pw"})
    assert r.status_code == 200
    r2 = client.post("/api/auth/signup", json={"username": "newuser", "password": "pw"})
    assert r2.status_code == 409


def test_chat_requires_auth(client):
    assert client.post("/api/chat", json={"question": "hi"}).status_code == 401


def test_chat_sync_returns_answer_inline(client):
    h = _auth(client)
    r = client.post("/api/chat_sync", json={"chat_id": "default", "question": "hello"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert "mock agent" in body["answer"]
    # both the question and the inline answer are persisted
    roles = [m["role"] for m in client.get("/api/history?chat_id=default", headers=h).json()["messages"]]
    assert "user" in roles and "assistant" in roles


def test_chat_enqueues_job_and_persists(client):
    h = _auth(client)
    r = client.post("/api/chat", json={"chat_id": "default", "question": "hello"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert "QUEUE:" in body["message"]
    job_id = body["job_id"]

    # BackgroundTasks run to completion when the TestClient request returns.
    job = client.get(f"/api/jobs/{job_id}", headers=h).json()
    assert job["status"] == "completed"
    assert "mock agent" in job["result"]

    # history has both the user question and the assistant answer
    roles = [m["role"] for m in client.get("/api/history?chat_id=default", headers=h).json()["messages"]]
    assert "user" in roles and "assistant" in roles
