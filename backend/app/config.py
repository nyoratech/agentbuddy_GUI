"""
Central configuration for the FinBuddy minimal backend.

Everything is driven by environment variables so the exact same code runs:

  * locally           -> talks to localhost RabbitMQ / Redis / SQLite
  * in docker-compose -> talks to the `rabbitmq` / `redis` / `postgres` services
  * in the cloud      -> talks to CloudAMQP / Redis Cloud / a managed Postgres

The resolution logic mirrors the full FinBuddy project (see
`db_light/message_queue/message_faststream.py`) so behaviour stays familiar.
"""
import os
import logging

logger = logging.getLogger("finbuddy.config")


def _running_in_docker() -> bool:
    return os.getenv("RUNNING_IN_DOCKER", "false").lower() == "true"


# --------------------------------------------------------------------------- #
# RabbitMQ (AMQP) - transport for job notifications                           #
# --------------------------------------------------------------------------- #
def get_rabbitmq_url() -> str:
    """
    Priority:
      1. CLOUDAMQP_URL  - CloudAMQP on GC/AWS (production / cloud)
      2. RABBITMQ_URL   - explicit override
      3. amqp://guest:guest@rabbitmq/       when RUNNING_IN_DOCKER=true
      4. amqp://guest:guest@localhost/      local development default
    """
    cloud = os.getenv("CLOUDAMQP_URL")
    if cloud:
        logger.info("RabbitMQ: using CLOUDAMQP_URL")
        return cloud

    explicit = os.getenv("RABBITMQ_URL")
    if explicit:
        logger.info("RabbitMQ: using RABBITMQ_URL=%s", explicit)
        return explicit

    if _running_in_docker():
        url = "amqp://guest:guest@rabbitmq/"
        logger.info("RabbitMQ: docker default %s", url)
        return url

    url = "amqp://guest:guest@localhost/"
    logger.info("RabbitMQ: localhost default %s", url)
    return url


# --------------------------------------------------------------------------- #
# Redis - lightweight job state / cache                                       #
# --------------------------------------------------------------------------- #
def get_redis_url() -> str:
    """
    Priority:
      1. REDIS_URL (full url, e.g. redis://:pass@host:port/0)  - cloud
      2. host/port/password env vars                            - Redis Cloud
      3. redis://redis:6379/0   when RUNNING_IN_DOCKER=true
      4. redis://localhost:6379/0   local default
    """
    full = os.getenv("REDIS_URL")
    if full:
        return full

    host = os.getenv("REDIS_HOST")
    if host:
        port = os.getenv("REDIS_PORT", "6379")
        password = os.getenv("REDIS_PASSWORD")
        user = os.getenv("REDIS_USERNAME", "default")
        if password:
            return f"redis://{user}:{password}@{host}:{port}/0"
        return f"redis://{host}:{port}/0"

    if _running_in_docker():
        return "redis://redis:6379/0"

    return "redis://localhost:6379/0"


# --------------------------------------------------------------------------- #
# Database - users + jobs + chat history                                      #
# --------------------------------------------------------------------------- #
def get_database_url() -> str:
    """
    Priority:
      1. DATABASE_URL (full SQLAlchemy url)      - explicit / cloud
      2. DB_HOST env vars                        - postgres in docker/cloud
      3. sqlite file in this directory           - zero-config local default
    """
    full = os.getenv("DATABASE_URL")
    if full:
        return full

    host = os.getenv("DB_HOST")
    if host:
        user = os.getenv("DB_USER", "finbuddy_app")
        password = os.getenv("DB_PASSWORD", "finbuddy_dev_password")
        name = os.getenv("DB_NAME", "finbuddy_db")
        port = os.getenv("DB_PORT", "5432")
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"

    # Zero-config local default: a SQLite file next to the app.
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "finbuddy_local.db")
    return f"sqlite:///{db_path}"


# --------------------------------------------------------------------------- #
# Misc                                                                         #
# --------------------------------------------------------------------------- #
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production-12345")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24)))

# Topic exchange every notification is published to (matches the main project).
JOBS_EXCHANGE = "jobs_exchange"

# How long the mock agent "thinks" before finishing, and how many progress
# updates it emits. Kept small so the demo feels responsive.
MOCK_JOB_STEPS = int(os.getenv("MOCK_JOB_STEPS", "3"))
MOCK_JOB_STEP_SECONDS = float(os.getenv("MOCK_JOB_STEP_SECONDS", "1.5"))

API_VERSION = "0.1.0-minimal"
