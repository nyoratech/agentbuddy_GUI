"""
FinBuddy — minimal backend.

A small FastAPI service that exposes just enough to drive the minimal frontend:

  POST /api/auth/login      -> JWT
  POST /api/auth/signup     -> create a user
  GET  /api/auth/me         -> whoami (requires token)
  POST /api/chat            -> enqueue a background "agent" job, returns job_id
  GET  /api/jobs/{job_id}   -> current job status/result (Redis cache, DB fallback)
  GET  /api/history         -> chat history for a user+chat
  GET  /health              -> health check

The heavy lifting (progress + completion notifications) happens asynchronously
in app.worker.run_job and is delivered to the frontend over RabbitMQ.
"""
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import db, cache
from .auth import create_access_token, get_current_user
from .config import API_VERSION
from .worker import run_job, mock_agent_reply

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("finbuddy.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    logger.info("Backend ready (version %s)", API_VERSION)
    yield


app = FastAPI(title="FinBuddy Minimal Backend", version=API_VERSION, lifespan=lifespan)

# The Reflex frontend runs on a different port, so allow cross-origin calls.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Schemas                                                                      #
# --------------------------------------------------------------------------- #
class Credentials(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    chat_id: str = "default"
    question: str


# --------------------------------------------------------------------------- #
# Health                                                                       #
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    return {"status": "healthy", "service": "finbuddy_minimal_backend", "version": API_VERSION}


# --------------------------------------------------------------------------- #
# Auth                                                                         #
# --------------------------------------------------------------------------- #
@app.post("/api/auth/login")
def login(creds: Credentials):
    user_id = db.authenticate(creds.username, creds.password)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )
    return {
        "access_token": create_access_token(user_id),
        "token_type": "bearer",
        "user_id": user_id,
    }


@app.post("/api/auth/signup")
def signup(creds: Credentials):
    if not creds.username or not creds.password:
        raise HTTPException(status_code=400, detail="username and password required")
    if not db.create_user(creds.username, creds.password):
        raise HTTPException(status_code=409, detail="username already exists")
    return {
        "access_token": create_access_token(creds.username),
        "token_type": "bearer",
        "user_id": creds.username,
    }


@app.get("/api/auth/me")
def me(user_id: str = Depends(get_current_user)):
    return {"user_id": user_id}


# --------------------------------------------------------------------------- #
# Chat -> background job                                                       #
# --------------------------------------------------------------------------- #
@app.post("/api/chat")
def chat(req: ChatRequest, background_tasks: BackgroundTasks,
         user_id: str = Depends(get_current_user)):
    """
    Persist the user's message and enqueue a background agent job.

    Returns immediately with a job_id; progress + the final answer arrive over
    RabbitMQ. This mirrors the real project's `QUEUE:{job_id}` contract.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is empty")

    job_id = str(uuid.uuid4())
    db.add_message(user_id, req.chat_id, "user", req.question)
    db.create_job(job_id, user_id, req.chat_id, req.question)

    background_tasks.add_task(run_job, job_id, user_id, req.chat_id, req.question)

    return {
        "job_id": job_id,
        "status": "queued",
        "message": f"Request received, working on it. QUEUE:{job_id}",
    }


@app.post("/api/chat_sync")
def chat_sync(req: ChatRequest, user_id: str = Depends(get_current_user)):
    """
    Synchronous chat: run the (mock) agent inline and return the answer now.

    This path needs no RabbitMQ/Redis, so it powers the zero-dependency local
    setup. The async /api/chat path above is the same thing done as a background
    job whose progress + answer stream back over RabbitMQ.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is empty")

    job_id = str(uuid.uuid4())
    db.add_message(user_id, req.chat_id, "user", req.question)
    db.create_job(job_id, user_id, req.chat_id, req.question)

    answer = mock_agent_reply(req.question)
    db.update_job(job_id, "completed", result=answer)
    db.add_message(user_id, req.chat_id, "assistant", answer)

    return {"job_id": job_id, "status": "completed", "answer": answer}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, user_id: str = Depends(get_current_user)):
    # Fast path: read the worker's Redis cache; fall back to the database.
    cached = cache.read_job(job_id)
    if cached:
        return {
            "job_id": job_id,
            "status": cached["status"],
            "result": cached["result"],
            "chat_id": cached.get("chat_id", ""),
        }
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "result": job.result,
        "chat_id": job.chat_id,
    }


@app.get("/api/history")
def history(chat_id: str = "default", user_id: str = Depends(get_current_user)):
    rows = db.get_history(user_id, chat_id)
    return {
        "chat_id": chat_id,
        "messages": [{"role": r.role, "content": r.content} for r in rows],
    }
