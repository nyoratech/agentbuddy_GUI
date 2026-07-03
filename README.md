# FinBuddy — an open-source GUI + framework for agentic AI in production

**FinBuddy is an open-source GUI *and* framework for building, running and
managing agentic AI in production — built entirely in
[Reflex.dev](https://reflex.dev) (pure Python, no JavaScript).**

It is two things at once:

- **A product surface for your agents** — a chat interface with persistent
  history, long-running jobs handled both synchronously and asynchronously, and
  rich outputs (Markdown, tables, interactive plots).
- **A control plane for operating them** — create, list, search and delete
  agents; manage the resources and data they use; enforce permissions and
  sharing across users and groups; expose agents as agentic services; and get
  analytics over it all. FastAPI + RabbitMQ + Redis + a SQL database underneath.

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

## Managing agents (the framework)

Beyond the chat surface, FinBuddy is a control plane for agents in production:

- **Agent lifecycle** — create, list, search and delete agents from the UI.
- **Resources & data** — register and manage the datasets, tools and resources
  agents are allowed to use.
- **Permissions & multi-tenancy** — PostgreSQL-backed role-based access control;
  share agents, chats and resources with specific users or groups.
- **Agentic services** — expose agents as callable services that other users and
  apps can invoke.
- **Analytics** — usage and performance analytics across your agentic services.

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

Two ways, depending on how much you want running. Three ready-made accounts are
pre-seeded so you can log straight in (signup is left out here because email
verification would need a working SMTP server):

| Username (email) | Password |
|---|---|
| `demo1@demo.com` | `demo1` |
| `demo2@demo2.com` | `demo2` |
| `demo3@demo.com` | `demo3` |

### ① Basic — no Docker, no services (fastest to try)

Runs with just Python and a local SQLite file. Chat answers come back
**synchronously**, so no RabbitMQ/Redis/PostgreSQL is required.

```bash
git clone <this-repo> && cd frontend_interface
./quickstart.sh
```

`quickstart.sh` creates a virtualenv, installs everything, prepares the database,
seeds the demo accounts, and starts both servers. When it's up, open
**http://localhost:3003** and log in with one of the accounts above.

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

Then open **http://localhost:3003** and log in with one of the accounts above.

| URL | What |
|---|---|
| http://localhost:3003 | The FinBuddy UI |
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
├── backend/               # FastAPI service + agent worker
│   └── app/{main,config,auth,db,cache,messaging,worker}.py
└── frontend/              # the Reflex UI (pure Python)
    ├── finbuddy/          # chat, sidebar/history, sharing, plots, auth
    ├── YourIndexingAI/    # agent "bot" + helpers
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

## Roadmap — coming soon

- **MCP servers** — first-class support for the Model Context Protocol: register
  MCP servers and expose their tools to agents.
- **Always-on MCP services** — long-running MCP services that stay up and serve
  agents continuously, not just per-request.
- **Analytics agents** — agents specialised in analytics that turn your data into
  metrics, tables and plots on demand.
- **Drag-and-drop agent builder** — a visual GUI to compose agents (tools,
  prompts, data, wiring) by dragging and dropping — no code required.

## Notes

- Sign-in uses the pre-seeded accounts above. In-app signup is intentionally not
  used here because it verifies the email via SMTP; the full app's
  Google/Microsoft OAuth and email verification are likewise not wired in.
- Chat sharing needs PostgreSQL (auto-provisioned by docker-compose); it degrades
  gracefully when Postgres is absent.

Built with [Reflex.dev](https://reflex.dev).
