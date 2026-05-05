"""
db.py — Direct Postgres access for model-runner.
Reads from public_marts; writes experiment status/results to public.experiments and public.experiment_results.
Reads SUPABASE_DB_URL from env (kept name during migration; rename to DB_URL post-cutover if desired).
"""

import json
import os
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


def _conn():
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL env var not set")
    return psycopg2.connect(db_url, connect_timeout=15)


def fetch_kpi_daily(start_date: str, end_date: str) -> List[dict]:
    """Fetch fact_kpi_daily for date range (CausalImpact inputs)."""
    with _conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT report_date, revenue, orders
               FROM public_marts.fact_kpi_daily
               WHERE report_date BETWEEN %s AND %s
               ORDER BY report_date""",
            (start_date, end_date),
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_kpi_geo_daily(
    start_date: str, end_date: str, geo_ids: Optional[List[str]] = None
) -> List[dict]:
    """Fetch fact_kpi_geo_daily for date range (GeoLift)."""
    sql = """SELECT report_date, geo_id, revenue, orders
             FROM public_marts.fact_kpi_geo_daily
             WHERE report_date BETWEEN %s AND %s"""
    params: list = [start_date, end_date]
    if geo_ids:
        sql += " AND geo_id = ANY(%s)"
        params.append(geo_ids)
    sql += " ORDER BY report_date"
    with _conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def fetch_tiktok_organic_daily(start_date: str, end_date: str) -> List[dict]:
    """Fetch fact_tiktok_organic_daily for date range (CausalImpact organic)."""
    with _conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """SELECT report_date, views, likes, comments, shares, followers
               FROM public_marts.fact_tiktok_organic_daily
               WHERE report_date BETWEEN %s AND %s
               ORDER BY report_date""",
            (start_date, end_date),
        )
        return [dict(r) for r in cur.fetchall()]


def insert_experiment(
    experiment_slug: str,
    experiment_type: str,
    start_date: str,
    end_date: str,
    config: Optional[dict] = None,
    status: str = "draft",
) -> Optional[dict]:
    """Insert or update experiment by slug; returns row (with id) for re-runs."""
    with _conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """INSERT INTO public.experiments
                 (experiment_slug, experiment_type, start_date, end_date, config, status)
               VALUES (%s, %s, %s, %s, %s::jsonb, %s)
               ON CONFLICT (experiment_slug) DO UPDATE SET
                 experiment_type = EXCLUDED.experiment_type,
                 start_date      = EXCLUDED.start_date,
                 end_date        = EXCLUDED.end_date,
                 config          = EXCLUDED.config,
                 status          = EXCLUDED.status
               RETURNING id, experiment_slug, status""",
            (
                experiment_slug,
                experiment_type,
                start_date,
                end_date,
                json.dumps(config or {}),
                status,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def upsert_experiment_results(experiment_id: int, results: List[dict]) -> None:
    """Upsert experiment_results. Each item: result_date, metric, value, interval_lower, interval_upper, metadata."""
    if not results:
        return
    rows = [
        (
            experiment_id,
            r["result_date"],
            r["metric"],
            r.get("value"),
            r.get("interval_lower"),
            r.get("interval_upper"),
            json.dumps(r["metadata"]) if isinstance(r.get("metadata"), dict) else r.get("metadata"),
        )
        for r in results
    ]
    with _conn() as conn, conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO public.experiment_results
                 (experiment_id, result_date, metric, value, interval_lower, interval_upper, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (experiment_id, result_date, metric) DO UPDATE SET
                 value          = EXCLUDED.value,
                 interval_lower = EXCLUDED.interval_lower,
                 interval_upper = EXCLUDED.interval_upper,
                 metadata       = EXCLUDED.metadata""",
            rows,
        )
        conn.commit()


def update_experiment_status(experiment_id: int, status: str) -> None:
    """Set experiments.status (e.g. running, completed, failed)."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE public.experiments SET status = %s WHERE id = %s",
            (status, experiment_id),
        )
        conn.commit()
