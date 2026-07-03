"""
Frontend-side configuration.

All of this runs *server-side* inside the Reflex backend process, so it reads
the same kind of environment variables as the FastAPI backend and resolves
local / docker / cloud endpoints the same way.
"""
import os


def _running_in_docker() -> bool:
    return os.getenv("RUNNING_IN_DOCKER", "false").lower() == "true"


def backend_url() -> str:
    """Base URL of the FastAPI backend the chat talks to."""
    explicit = os.getenv("BACKEND_URL")
    if explicit:
        return explicit.rstrip("/")
    if _running_in_docker():
        return "http://backend:8008"
    return "http://localhost:8008"


def rabbitmq_url() -> str:
    """RabbitMQ URL for the notification consumer (mirrors backend resolution)."""
    cloud = os.getenv("CLOUDAMQP_URL")
    if cloud:
        return cloud
    explicit = os.getenv("RABBITMQ_URL")
    if explicit:
        return explicit
    if _running_in_docker():
        return "amqp://guest:guest@rabbitmq/"
    return "amqp://guest:guest@localhost/"


JOBS_EXCHANGE = "jobs_exchange"
