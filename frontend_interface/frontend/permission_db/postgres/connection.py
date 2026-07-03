"""
Shared PostgreSQL connection pool for finbuddy.

This module provides a connection pool that all database modules should use.
It replaces the DuckDB connections for transactional data (agents, GUI, etc.)

Usage:
    from db_light.postgres.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM agents WHERE user_id = %s", [user_id])
            results = cur.fetchall()
"""

import os
import logging
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[SimpleConnectionPool] = None


def init_pool(
    host: str = None,
    port: int = 5432,
    database: str = "finbuddy_db",
    user: str = "finbuddy_app",
    password: str = None,
    minconn: int = 2,
    maxconn: int = 20
):
    """
    Initialize the PostgreSQL connection pool.

    Call this once at application startup.

    Args:
        host: Database host (default: from env DB_HOST or 'localhost')
        port: Database port (default: 5432)
        database: Database name (default: 'finbuddy_db')
        user: Database user (default: 'finbuddy_app')
        password: Database password (default: from env DB_PASSWORD)
        minconn: Minimum connections in pool (default: 2)
        maxconn: Maximum connections in pool (default: 20)
    """
    global _pool

    if _pool is not None:
        logger.warning("Connection pool already initialized")
        return

    # Get config from environment if not provided
    host = host or os.getenv("DB_HOST", "localhost")
    password = password or os.getenv("DB_PASSWORD", "finbuddy_dev_password")

    try:
        _pool = SimpleConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            # Connection options
            connect_timeout=10,
            options="-c statement_timeout=30000"  # 30 second query timeout
        )
        logger.info(f"✅ PostgreSQL connection pool initialized: {database}@{host}:{port}")
    except Exception as e:
        logger.error(f"❌ Failed to initialize PostgreSQL connection pool: {e}")
        raise


@contextmanager
def get_connection(read_only: bool = False, dict_cursor: bool = True):
    """
    Get a database connection from the pool.

    This is a context manager that automatically handles:
    - Getting connection from pool
    - Committing on success
    - Rolling back on error
    - Returning connection to pool

    Args:
        read_only: If True, set connection to read-only mode
        dict_cursor: If True, return rows as dictionaries (default: True)

    Usage:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM agents")
                results = cur.fetchall()  # Returns list of dicts

    Raises:
        RuntimeError: If connection pool not initialized
    """
    if _pool is None:
        raise RuntimeError(
            "Connection pool not initialized. Call init_pool() first "
            "(usually in your FastAPI startup event)."
        )

    conn = None
    try:
        # Get connection from pool
        conn = _pool.getconn()

        # Set read-only mode if requested
        if read_only:
            conn.set_session(readonly=True, autocommit=True)

        # Yield connection
        yield conn

        # Commit if not read-only
        if not read_only:
            conn.commit()

    except Exception as e:
        # Rollback on error
        if conn and not read_only:
            conn.rollback()
        logger.error(f"Database error: {e}", exc_info=True)
        raise

    finally:
        # Reset read-only mode and return to pool
        if conn:
            if read_only:
                conn.set_session(readonly=False, autocommit=False)
            _pool.putconn(conn)


def get_dict_cursor(conn):
    """
    Get a cursor that returns rows as dictionaries.

    Usage:
        with get_connection() as conn:
            cur = get_dict_cursor(conn)
            cur.execute("SELECT * FROM agents")
            results = cur.fetchall()
            # results = [{'id': '123', 'name': 'agent1', ...}, ...]
    """
    return conn.cursor(cursor_factory=RealDictCursor)


def close_pool():
    """
    Close all connections in the pool.

    Call this on application shutdown.
    """
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("PostgreSQL connection pool closed")


def health_check() -> bool:
    """
    Check if database connection is healthy.

    Returns:
        True if database is accessible, False otherwise
    """
    try:
        with get_connection(read_only=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                return result is not None
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


# ============================================================
# PERMISSION HELPERS
# ============================================================

def set_current_user(conn, user_id: str):
    """
    Set the current user ID for Row-Level Security.

    This should be called after getting a connection, before querying.

    Args:
        conn: Database connection
        user_id: Current user ID

    Usage:
        with get_connection() as conn:
            set_current_user(conn, current_user['user_id'])
            with conn.cursor() as cur:
                # Now RLS policies will enforce user's permissions
                cur.execute("SELECT * FROM agents")
    """
    with conn.cursor() as cur:
        cur.execute("SET LOCAL app.current_user_id = %s", [user_id])


def check_permission(conn, user_id: str, resource_id: str, permission: str = 'read') -> bool:
    """
    Check if user has permission to access a resource.

    Args:
        conn: Database connection
        user_id: User ID to check
        resource_id: Resource ID (agent_id, tool_id, etc.)
        permission: Required permission level ('read', 'write', 'admin')

    Returns:
        True if user has permission, False otherwise

    Usage:
        with get_connection(read_only=True) as conn:
            if check_permission(conn, user_id, agent_id, 'write'):
                # User can write to this agent
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT has_resource_permission(%s, %s, %s) as has_perm",
            [user_id, resource_id, permission]
        )
        result = cur.fetchone()
        return result[0] if result else False


def log_action(
    conn,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str = None,
    details: dict = None,
    ip_address: str = None
):
    """
    Log an action to the audit log.

    Args:
        conn: Database connection
        user_id: User performing the action
        action: Action type ('create', 'read', 'update', 'delete', 'share')
        resource_type: Type of resource ('agent', 'tool', 'page_layout')
        resource_id: ID of resource (optional)
        details: Additional context as JSON (optional)
        ip_address: User's IP address (optional)

    Usage:
        with get_connection() as conn:
            # Create agent
            cur.execute("INSERT INTO agents ...")

            # Log it
            log_action(conn, user_id, 'create', 'agent', agent_id,
                      details={'name': 'My Agent'})
    """
    import json
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO audit_log (user_id, action, resource_type, resource_id, details, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, [
            user_id,
            action,
            resource_type,
            resource_id,
            json.dumps(details) if details else None,
            ip_address
        ])
