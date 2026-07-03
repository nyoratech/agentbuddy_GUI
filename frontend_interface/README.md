# FinBuddy — an open-source GUI for agentic AI

**FinBuddy is an open-source graphical interface for agentic AI, built entirely
in [Reflex.dev](https://reflex.dev) — pure Python, no JavaScript.**

It gives your AI agents a real product surface instead of a bare terminal: a
chat interface with persistent history, long-running jobs handled both
synchronously and asynchronously, rich outputs (Markdown, tables, interactive
plots), user accounts with permissions and sharing, and a production-shaped
backend (FastAPI + RabbitMQ + Redis + a SQL database).

This repository is a **self-contained, runnable demo**. The agent itself is a
**mock** that echoes your request — swap it for a real agent and nothing else in
the pipeline changes.

---

## Features

- **💬 Chat with persistent history** — every chat, message and generated plot is
  saved per user and restored when you log back in.
- **🗂️ Organised & shareable** — group chats into folders in the sidebar, and share
  a chat with other users or groups through built-in role-based permissions.
- **⚡ Synchronous *and* asynchronous jobs** — short requests are answered inline;
  long-running work runs as a background job that streams progress and results
  back to the UI live.
- **📈 Rich outputs** — answers render Markdown, data tables and interactive plots,
  not just text.
- **🔐 Auth & permissions** — username/password accounts with JWT sessions, plus
  PostgreSQL-backed role-based access control for sharing.
- **🧱 Production-shaped backend** — a **FastAPI** service, **RabbitMQ (AMQP)** as the
  job/notification bus, **Redis** for fast job state, and **SQLite or PostgreSQL**
  for durable storage.

## Architecture

```
  Reflex UI  <->  FastAPI backend  <->  RabbitMQ + Redis  <->  your agent
      |                 |
      |                 +- background jobs -> progress + results (async)
      +- auth · chat history · plots  -->  SQLite / PostgreSQL
```

- The UI logs you in against its own database and mints a JWT.
- Sending a chat calls the backend. In **synchronous** mode the answer is returned
  inline; in **asynchronous** mode the backend enqueues a job and the answer +
  progress stream back over RabbitMQ to a live consumer in the UI.
- Redis caches job state; PostgreSQL holds the RBAC data used for sharing.

---

## Run it

Two ways, depending on how much you want running. Both log you in as
**`demo` / `demo`** (or sign up in the UI).

### ① Basic — no Docker, no services (fastest to try)

Runs with just Python and a local SQLite file. Chat answers come back
**synchronously**, so no RabbitMQ/Redis/PostgreSQL is required.

```bash
git clone <this-repo> && cd frontend_interface
./quickstart.sh
```

`quickstart.sh` creates a virtualenv, installs everything, prepares the database,
seeds the demo user, and starts both servers. When it's up, open
**http://localhost:3000** and log in as `demo` / `demo`.

> Requires Python 3.11+. First run takes a couple of minutes (dependency install
> + one-time UI compile).

### ② Full — everything in Docker (live async experience)

One command brings up the UI, backend, **RabbitMQ**, **Redis** and **PostgreSQL**,
running in **asynchronous** mode with live job notifications and working chat
sharing.

```bash
cd frontend_interface
docker compose up --build
```

Then open **http://localhost:3000** (login `demo` / `demo`).

| URL | What |
|---|---|
| http://localhost:3000 | The FinBuddy UI |
| http://localhost:8008/docs | Backend API docs |
| http://localhost:15672 | RabbitMQ management UI (guest / guest) |

### Configuration

Copy `.env.example` to `.env` to override anything. Sensible defaults mean an
empty `.env` works for both local and Docker. Key switches:

- `USE_ASYNC_JOBS` — `false` (default, sync/no broker) or `true` (background jobs
  over RabbitMQ). docker-compose sets this to `true`.
- `JWT_SECRET_KEY` — must be identical for frontend and backend.
- `DATABASE_URL` / `CLOUDAMQP_URL` / `REDIS_URL` — point at cloud services when
  deploying (Postgres, CloudAMQP, Redis Cloud).

---

## Project layout

```
frontend_interface/
├── docker-compose.yml     # postgres + redis + rabbitmq + backend + frontend
├── quickstart.sh          # one-command local run (no Docker)
├── run_tests.sh
├── backend/               # FastAPI service + mock agent worker
│   └── app/{main,config,auth,db,cache,messaging,worker}.py
└── frontend/              # the Reflex UI (pure Python)
    ├── finbuddy/          # chat, sidebar/history, sharing, plots, auth
    ├── YourIndexingAI/    # shim: mock agent "bot" + helpers
    ├── db_light/          # shim: JWT / auth helpers
    └── permission_db/     # RBAC (sharing) — connection + schema
```

## Testing

```bash
cd frontend_interface
./run_tests.sh
```

Covers the backend API (login, chat → job → completion), the messaging contract,
the Redis cache, the frontend shims, and chat-history persistence
(user → chat → message → plot → reload). A live RabbitMQ round-trip test runs
when a broker is available and skips otherwise.

## Notes & limitations (by design)

- The agent is a **mock** — no real LLM/tools run. Plots render when plot data
  exists; the mock produces none.
- Login/signup use username + password against the local DB (the full app's
  Google/Microsoft OAuth and email verification are not wired in this demo).
- Chat sharing needs PostgreSQL (auto-provisioned by docker-compose); it degrades
  gracefully when Postgres is absent.

Built with [Reflex.dev](https://reflex.dev).
