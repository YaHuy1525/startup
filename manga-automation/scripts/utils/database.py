"""
PostgreSQL connection helper using psycopg2.
Provides a context-manager cursor and simple execute helpers.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from contextlib import contextmanager
from typing import Any, Optional

_pool: Optional[SimpleConnectionPool] = None


def _get_pool() -> SimpleConnectionPool:
    global _pool
    if _pool is None:
        dsn = (
            os.environ.get("DATABASE_URL")
            or os.environ.get("SUPABASE_DB_URL")
            or os.environ.get("SUPABASE_DATABASE_URL")
            or ""
        ).strip()
        if not dsn:
            raise KeyError(
                "DATABASE_URL (or SUPABASE_DB_URL) is not set — required for Postgres/Supabase"
            )
        _pool = SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=dsn,
        )
    return _pool


@contextmanager
def get_cursor():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        pool.putconn(conn)


def execute(query: str, params: tuple = ()) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(query, params)
        try:
            return [dict(r) for r in cur.fetchall()]
        except psycopg2.ProgrammingError:
            return []


def execute_one(query: str, params: tuple = ()) -> Optional[dict]:
    with get_cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute_returning(query: str, params: tuple = ()) -> Optional[Any]:
    """Execute INSERT/UPDATE RETURNING and return the first column of first row."""
    with get_cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if row:
            return list(dict(row).values())[0]
        return None
