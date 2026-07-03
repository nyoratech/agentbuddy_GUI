import os
import reflex as rx

# The chat history / plots / sharing live in this DB. SQLite by default (local,
# zero-config); set DATABASE_URL to point at Postgres in docker/cloud.
database_url = os.getenv("DATABASE_URL", "sqlite:///reflex.db")

config = rx.Config(
    app_name="finbuddy",
    db_url=database_url,
    frontend_port=3003,
    backend_port=8003,
    backend_host="0.0.0.0",
)
