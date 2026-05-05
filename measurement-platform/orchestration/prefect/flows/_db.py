"""Shared psycopg2 helpers for Prefect flows.

Replaces direct Supabase REST API usage. Reads SUPABASE_DB_URL (kept for now to
avoid renaming env vars during migration; can be renamed to DB_URL post-cutover).
"""

from __future__ import annotations

import os
from typing import Any


def get_conn():
    """Return a psycopg2 connection, or None if SUPABASE_DB_URL is unset."""
    import psycopg2

    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        return None
    return psycopg2.connect(db_url, connect_timeout=15)


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SELECT and return rows as list of dicts. Returns [] on no connection."""
    conn = get_conn()
    if not conn:
        return []
    try:
        import psycopg2.extras

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> bool:
    """Run an INSERT/UPDATE/DELETE. Returns True on success, False if no connection.
    Re-raises on SQL errors so callers can log them."""
    conn = get_conn()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
