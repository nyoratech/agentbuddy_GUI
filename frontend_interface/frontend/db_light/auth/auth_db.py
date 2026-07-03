"""
Shim for db_light.auth.auth_db.

The full project keeps a PostgreSQL RBAC user table in sync with the Reflex DB.
The only function the frontend imports is `ensure_user_exists`. Here it is made
**exception-safe**: when Postgres is reachable (docker/cloud) it creates the RBAC
user so sharing works; when it is not (plain local dev) it simply returns False
without raising, so login/signup still succeed against the Reflex DB.
"""
import os
import logging

logger = logging.getLogger("finbuddy.shim.auth_db")


def _connect():
    import psycopg2
    db_host = os.getenv("DB_HOST")
    password = os.getenv("DB_PASSWORD", "finbuddy_dev_password")
    hosts = [db_host] if db_host else ["localhost", "finbuddy_postgres", "postgres"]
    last_error = None
    for host in hosts:
        try:
            return psycopg2.connect(
                host=host, port=int(os.getenv("DB_PORT", "5432")),
                database=os.getenv("DB_NAME", "finbuddy_db"),
                user=os.getenv("DB_USER", "finbuddy_app"),
                password=password,
            )
        except Exception as exc:  # noqa: BLE001 - try the next host
            last_error = exc
    raise last_error if last_error else RuntimeError("no db host")


def ensure_user_exists(user_id: str, company_id: str = "default") -> bool:
    """Create the RBAC user in Postgres if reachable; never raise."""
    try:
        conn = _connect()
    except Exception as exc:  # Postgres not available -> sharing disabled, login still works
        logger.info("Postgres unavailable, skipping RBAC user sync for %s (%s)", user_id, exc)
        return False
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
        if cur.fetchone():
            return True
        cur.execute(
            "INSERT INTO users (user_id, username, company_id, password_hash) "
            "VALUES (%s, %s, %s, %s)",
            (user_id, user_id, company_id, "reflex_auth"),
        )
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("Error creating RBAC user %s: %s", user_id, exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()
