"""
db.py — Supabase client for model-runner (read marts, write experiment_results).
Uses SUPABASE_URL and SUPABASE_SERVICE_KEY from env.
For marts (public_marts schema), uses SUPABASE_DB_URL if set; else Supabase REST API.
"""

import os
from typing import Any, List, Optional

try:
    from supabase import create_client, Client
    _HAS_SUPABASE = True
except ImportError:
    _HAS_SUPABASE = False
    Client = Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    _HAS_PSYCOPG2 = True
except ImportError:
    _HAS_PSYCOPG2 = False


def get_supabase() -> Optional[Client]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    if not _HAS_SUPABASE:
        raise RuntimeError("supabase package not installed; pip install supabase")
    return create_client(url, key)


def _get_db_conn():
    """Get psycopg2 connection for public_marts. Set SUPABASE_DB_URL (from Supabase > Settings > Database > Connection string)."""
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        return None
    return psycopg2.connect(db_url)


def _client_slug() -> str:
    return os.environ.get("CLIENT_SLUG", "default")


def fetch_kpi_daily(supabase: Client, start_date: str, end_date: str) -> List[dict]:
    """Fetch fact_kpi_daily for date range (for CausalImpact inputs)."""
    slug = _client_slug()
    if _HAS_PSYCOPG2:
        conn = _get_db_conn()
        if conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """SELECT report_date, revenue, orders FROM public_marts.fact_kpi_daily
                           WHERE client_slug = %s AND report_date >= %s AND report_date <= %s ORDER BY report_date""",
                        (slug, start_date, end_date),
                    )
                    return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()
    try:
        r = supabase.schema("public_marts").table("fact_kpi_daily").select(
            "report_date,revenue,orders"
        ).eq("client_slug", slug).gte("report_date", start_date).lte("report_date", end_date).order("report_date").execute()
        return r.data if hasattr(r, "data") else []
    except Exception:
        return []


def fetch_kpi_geo_daily(
    supabase: Client, start_date: str, end_date: str, geo_ids: Optional[List[str]] = None
) -> List[dict]:
    """Fetch fact_kpi_geo_daily for date range (for GeoLift)."""
    slug = _client_slug()
    conn = _get_db_conn()
    if conn and _HAS_PSYCOPG2:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                sql = """SELECT report_date, geo_id, revenue, orders FROM public_marts.fact_kpi_geo_daily
                         WHERE client_slug = %s AND report_date >= %s AND report_date <= %s"""
                params: list = [slug, start_date, end_date]
                if geo_ids:
                    sql += " AND geo_id = ANY(%s)"
                    params.append(geo_ids)
                sql += " ORDER BY report_date"
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    try:
        q = supabase.schema("public_marts").table("fact_kpi_geo_daily").select(
            "report_date,geo_id,revenue,orders"
        ).eq("client_slug", slug).gte("report_date", start_date).lte("report_date", end_date)
        if geo_ids:
            q = q.in_("geo_id", geo_ids)
        r = q.order("report_date").execute()
        return r.data if hasattr(r, "data") else []
    except Exception:
        return []


def fetch_tiktok_organic_daily(supabase: Client, start_date: str, end_date: str) -> List[dict]:
    """Fetch fact_tiktok_organic_daily for date range (CausalImpact organic)."""
    slug = _client_slug()
    conn = _get_db_conn()
    if conn and _HAS_PSYCOPG2:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT report_date, views, likes, comments, shares, followers
                       FROM public_marts.fact_tiktok_organic_daily
                       WHERE client_slug = %s AND report_date >= %s AND report_date <= %s ORDER BY report_date""",
                    (slug, start_date, end_date),
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    try:
        r = supabase.schema("public_marts").table("fact_tiktok_organic_daily").select(
            "report_date,views,likes,comments,shares,followers"
        ).eq("client_slug", slug).gte("report_date", start_date).lte("report_date", end_date).order("report_date").execute()
        return r.data if hasattr(r, "data") else []
    except Exception:
        return []


def insert_experiment(
    supabase: Client,
    experiment_slug: str,
    experiment_type: str,
    start_date: str,
    end_date: str,
    config: Optional[dict] = None,
    status: str = "draft",
) -> Optional[dict]:
    """Insert or update experiment by slug; returns row (for re-runs, updates existing)."""
    row = {
        "client_slug": _client_slug(),
        "experiment_slug": experiment_slug,
        "experiment_type": experiment_type,
        "start_date": start_date,
        "end_date": end_date,
        "config": config or {},
        "status": status,
    }
    r = supabase.table("experiments").upsert(row, on_conflict="client_slug,experiment_slug").execute()
    if hasattr(r, "data") and r.data:
        return r.data[0]
    return None


def upsert_experiment_results(
    supabase: Client,
    experiment_id: int,
    results: List[dict],
) -> None:
    """Upsert experiment_results. Each item: result_date, metric, value, interval_lower, interval_upper, metadata."""
    rows = [
        {
            "experiment_id": experiment_id,
            "result_date": d["result_date"],
            "metric": d["metric"],
            "value": d.get("value"),
            "interval_lower": d.get("interval_lower"),
            "interval_upper": d.get("interval_upper"),
            "metadata": d.get("metadata"),
        }
        for d in results
    ]
    supabase.table("experiment_results").upsert(rows, on_conflict="experiment_id,result_date,metric").execute()


def update_experiment_status(supabase: Client, experiment_id: int, status: str) -> None:
    """Set experiments.status (e.g. running, completed, failed)."""
    supabase.table("experiments").update({"status": status}).eq("id", experiment_id).execute()
