"""
Database layer: users, chat messages and jobs.

Uses SQLModel so the same models work on SQLite (local, zero-config) and on
PostgreSQL (docker-compose / cloud). The connection string is resolved in
`config.get_database_url()`.

This is deliberately tiny — it only persists what the minimal interface needs:
who the users are, what they said, and the state of their background jobs.
"""
import datetime as dt
import hashlib
import logging
from typing import Optional, List

from sqlmodel import SQLModel, Field, Session, create_engine, select

from .config import get_database_url

logger = logging.getLogger("finbuddy.db")


# --------------------------------------------------------------------------- #
# Models                                                                       #
# --------------------------------------------------------------------------- #
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str


class ChatMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    chat_id: str = Field(index=True)
    role: str  # "user" or "assistant"
    content: str
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(index=True, unique=True)
    user_id: str = Field(index=True)
    chat_id: str = Field(index=True)
    prompt: str
    status: str = "queued"  # queued -> in_progress -> completed / failed
    result: str = ""
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


# --------------------------------------------------------------------------- #
# Engine / session helpers                                                     #
# --------------------------------------------------------------------------- #
_DB_URL = get_database_url()
_connect_args = {"check_same_thread": False} if _DB_URL.startswith("sqlite") else {}
engine = create_engine(_DB_URL, echo=False, connect_args=_connect_args)


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_db() -> None:
    """Create tables and seed a demo user (demo / demo)."""
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == "demo")).first()
        if not existing:
            session.add(User(username="demo", password_hash=_hash_password("demo")))
            session.commit()
            logger.info("Seeded demo user: demo / demo")


def get_session() -> Session:
    return Session(engine)


# --------------------------------------------------------------------------- #
# CRUD used by the API / worker                                                #
# --------------------------------------------------------------------------- #
def authenticate(username: str, password: str) -> Optional[str]:
    """Return the username if credentials are valid, else None."""
    with get_session() as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if user and user.password_hash == _hash_password(password):
            return user.username
    return None


def create_user(username: str, password: str) -> bool:
    with get_session() as session:
        if session.exec(select(User).where(User.username == username)).first():
            return False
        session.add(User(username=username, password_hash=_hash_password(password)))
        session.commit()
        return True


def add_message(user_id: str, chat_id: str, role: str, content: str) -> None:
    with get_session() as session:
        session.add(ChatMessage(user_id=user_id, chat_id=chat_id, role=role, content=content))
        session.commit()


def get_history(user_id: str, chat_id: str, limit: int = 100) -> List[ChatMessage]:
    with get_session() as session:
        rows = session.exec(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id, ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.id)
            .limit(limit)
        ).all()
        return list(rows)


def create_job(job_id: str, user_id: str, chat_id: str, prompt: str) -> None:
    with get_session() as session:
        session.add(Job(job_id=job_id, user_id=user_id, chat_id=chat_id, prompt=prompt))
        session.commit()


def update_job(job_id: str, status: str, result: Optional[str] = None) -> None:
    with get_session() as session:
        job = session.exec(select(Job).where(Job.job_id == job_id)).first()
        if job:
            job.status = status
            if result is not None:
                job.result = result
            session.add(job)
            session.commit()


def get_job(job_id: str) -> Optional[Job]:
    with get_session() as session:
        return session.exec(select(Job).where(Job.job_id == job_id)).first()
