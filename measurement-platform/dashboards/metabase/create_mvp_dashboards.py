#!/usr/bin/env python3
"""
Create MVP dashboards in Metabase via API (Executive Overview first).
Uses session login or API key. Run after Metabase is connected to Supabase.

Env:
  METABASE_URL     e.g. http://localhost:3000 (default)
  METABASE_EMAIL   admin email (for session login)
  METABASE_PASSWORD  admin password (for session login)
  METABASE_API_KEY   optional; if set, used instead of session
"""
from __future__ import annotations

import os
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

METABASE_URL = os.environ.get("METABASE_URL", "http://localhost:3000").rstrip("/")
METABASE_EMAIL = os.environ.get("METABASE_EMAIL", "")
METABASE_PASSWORD = os.environ.get("METABASE_PASSWORD", "")
METABASE_API_KEY = os.environ.get("METABASE_API_KEY", "")


def get_headers(session_id: str | None) -> dict:
    if METABASE_API_KEY:
        return {"Content-Type": "application/json", "x-api-key": METABASE_API_KEY}
    if session_id:
        return {"Content-Type": "application/json", "X-Metabase-Session": session_id}
    return {"Content-Type": "application/json"}


def login() -> str | None:
    if METABASE_API_KEY:
        return "api_key"
    if not METABASE_EMAIL or not METABASE_PASSWORD:
        print("Set METABASE_EMAIL and METABASE_PASSWORD, or METABASE_API_KEY", file=sys.stderr)
        return None
    r = requests.post(
        f"{METABASE_URL}/api/session",
        json={"username": METABASE_EMAIL, "password": METABASE_PASSWORD},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"Login failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return None
    return r.json().get("id")


def get_database_id(headers: dict, database_id: int | None = None, database_name: str | None = None) -> int | None:
    """Return a Metabase database id.

    If *database_id* is given, return it directly (caller knows the id).
    If *database_name* is given, find the DB with that name.
    Otherwise return the first non-sample DB (legacy behaviour).
    """
    if database_id:
        return database_id
    r = requests.get(f"{METABASE_URL}/api/database", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"GET /api/database failed: {r.status_code}", file=sys.stderr)
        return None
    data = r.json()
    dbs = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(dbs, list):
        dbs = []
    if database_name:
        for db in dbs:
            if db.get("name") == database_name:
                return db["id"]
        print(f"Database '{database_name}' not found in Metabase.", file=sys.stderr)
        return None
    for db in dbs:
        if db.get("is_sample") or db.get("name") == "Sample Database":
            continue
        return db["id"]
    return None


def list_databases(headers: dict) -> list[dict]:
    """Return all non-sample databases (useful for multi-client listing)."""
    r = requests.get(f"{METABASE_URL}/api/database", headers=headers, timeout=30)
    if r.status_code != 200:
        return []
    data = r.json()
    dbs = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(dbs, list):
        return []
    return [db for db in dbs if not db.get("is_sample") and db.get("name") != "Sample Database"]


def _client_slug_tag() -> dict:
    """Template tag for client_slug filter."""
    import uuid
    return {
        "client_slug": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "client_slug",
            "display-name": "Client",
            "type": "text",
            "default": "default",
        },
    }


def create_card(
    headers: dict,
    database_id: int,
    name: str,
    sql: str,
    display: str = "line",
    viz_settings: dict | None = None,
    template_tags: dict | None = None,
) -> dict | None:
    tags = template_tags if template_tags is not None else _client_slug_tag()
    payload = {
        "name": name,
        "database_id": database_id,
        "dataset_query": {
            "type": "native",
            "native": {"query": sql, "template-tags": tags},
            "database": database_id,
        },
        "display": display,
        "visualization_settings": viz_settings or {},
    }
    r = requests.post(f"{METABASE_URL}/api/card", json=payload, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        print(f"Create card '{name}' failed: {r.status_code} {r.text[:300]}", file=sys.stderr)
        return None
    return r.json()


def list_dashboards(headers: dict) -> list[dict]:
    r = requests.get(f"{METABASE_URL}/api/dashboard", headers=headers, timeout=30)
    if r.status_code != 200:
        return []
    data = r.json()
    if isinstance(data, list):
        return data
    return data.get("dashboards", data.get("data", []))


def create_dashboard(headers: dict, name: str) -> dict | None:
    r = requests.post(
        f"{METABASE_URL}/api/dashboard",
        json={"name": name},
        headers=headers,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        print(f"Create dashboard '{name}' failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return None
    return r.json()


def add_card_to_dashboard(
    headers: dict, dashboard_id: int, card_id: int, row: int, col: int, size_x: int = 8, size_y: int = 4
) -> bool:
    # Metabase API: cardId, parameter_mappings (required array), dashboard-card
    payload = {
        "cardId": card_id,
        "parameter_mappings": [],
        "dashboard-card": {"card_id": card_id},
        "row": row,
        "col": col,
        "sizeX": size_x,
        "sizeY": size_y,
    }
    r = requests.post(
        f"{METABASE_URL}/api/dashboard/{dashboard_id}/cards",
        json=payload,
        headers=headers,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        # Fallback: use PUT /api/dashboard/:id to update dashcards (Metabase 0.48+)
        return _add_card_via_put(headers, dashboard_id, card_id, row, col, size_x, size_y)
    return True


def _add_card_via_put(
    headers: dict, dashboard_id: int, card_id: int, row: int, col: int, size_x: int, size_y: int
) -> bool:
    """Add card via PUT dashboard when POST /cards returns 404 (newer Metabase)."""
    r = requests.get(f"{METABASE_URL}/api/dashboard/{dashboard_id}", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"GET dashboard {dashboard_id} failed: {r.status_code}", file=sys.stderr)
        return False
    dash = r.json()
    dashcards = list(dash.get("dashcards", []))
    # Build new dashcard - use negative id as temp id (Metabase frontend convention for new items)
    new_dashcard = {
        "id": -card_id,  # temporary id for new dashcard (server assigns real id on save)
        "card_id": card_id,
        "row": row,
        "col": col,
        "size_x": size_x,
        "size_y": size_y,
        "parameter_mappings": [],
        "series": [],
    }
    # Strip read-only fields from existing dashcards, keep id/card_id/row/col/size/params/series
    clean_cards = []
    for dc in dashcards:
        clean_cards.append(
            {k: v for k, v in dc.items() if k in ("id", "card_id", "row", "col", "size_x", "size_y", "parameter_mappings", "series")}
        )
    clean_cards.append(new_dashcard)
    dashcards = clean_cards
    r = requests.put(
        f"{METABASE_URL}/api/dashboard/{dashboard_id}",
        json={"dashcards": dashcards},
        headers=headers,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        print(f"Add card {card_id} via PUT failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return False
    return True


# Client filter — all queries include WHERE client_slug = {{client_slug}}
_CF = "client_slug = {{client_slug}}"

# Executive Overview: questions from MVP spec (public_marts)
EXEC_OVERVIEW_QUESTIONS = [
    {
        "name": "Daily revenue",
        "sql": f"SELECT report_date AS date, COALESCE(SUM(revenue), 0) AS revenue FROM public_marts.fact_kpi_daily WHERE {_CF} GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["revenue"]},
    },
    {
        "name": "Daily orders",
        "sql": f"SELECT report_date AS date, COALESCE(SUM(orders), 0) AS orders FROM public_marts.fact_kpi_daily WHERE {_CF} GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["orders"]},
    },
    {
        "name": "Spend by date",
        "sql": f"SELECT report_date AS date, COALESCE(SUM(spend), 0) AS spend FROM public_marts.fact_spend_daily WHERE {_CF} GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["spend"]},
    },
    {
        "name": "Total spend by channel",
        "sql": f"SELECT channel, COALESCE(SUM(spend), 0) AS spend FROM public_marts.fact_spend_daily WHERE {_CF} GROUP BY channel ORDER BY spend DESC",
        "display": "bar",
        "viz": {"graph.dimensions": ["channel"], "graph.metrics": ["spend"]},
    },
    {
        "name": "ROAS (revenue / spend)",
        "sql": f"""SELECT
  (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily WHERE {_CF}) AS revenue,
  (SELECT COALESCE(SUM(spend), 0) FROM public_marts.fact_spend_daily WHERE {_CF}) AS spend,
  CASE WHEN (SELECT COALESCE(SUM(spend), 0) FROM public_marts.fact_spend_daily WHERE {_CF}) = 0 THEN 0
       ELSE (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily WHERE {_CF})
            / NULLIF((SELECT SUM(spend) FROM public_marts.fact_spend_daily WHERE {_CF}), 0) END AS roas""",
        "display": "table",
        "viz": {},
    },
]

# Dashboard 3: Email / Klaviyo
EMAIL_KLAVIYO_QUESTIONS = [
    {
        "name": "Email sends by day",
        "sql": f"SELECT report_date AS date, COALESCE(SUM(sent), 0) AS sent FROM public_marts.fact_klaviyo_daily WHERE {_CF} GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["sent"]},
    },
    {
        "name": "Email opens and clicks by day",
        "sql": f"SELECT report_date AS date, COALESCE(SUM(opens), 0) AS opens, COALESCE(SUM(clicks), 0) AS clicks FROM public_marts.fact_klaviyo_daily WHERE {_CF} GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["opens", "clicks"]},
    },
    {
        "name": "Klaviyo campaigns summary",
        "sql": f"SELECT campaign_id, report_date, sent, opens, clicks FROM public_marts.fact_klaviyo_daily WHERE {_CF} ORDER BY report_date DESC, campaign_id LIMIT 50",
        "display": "table",
        "viz": {},
    },
]

# Dashboard 4: Experiment Results
EXPERIMENT_RESULTS_QUESTIONS = [
    {
        "name": "Experiments list",
        "sql": f"SELECT id, experiment_slug, experiment_type, start_date, end_date, status, config FROM public.experiments WHERE {_CF} ORDER BY id DESC",
        "display": "table",
        "viz": {},
    },
    {
        "name": "Lift over time (by experiment)",
        "sql": f"""SELECT e.experiment_slug, r.result_date AS date, r.metric, r.value, r.interval_lower, r.interval_upper
FROM public.experiment_results r
JOIN public.experiments e ON e.id = r.experiment_id
WHERE e.{_CF}
ORDER BY e.experiment_slug, r.result_date""",
        "display": "line",
        "viz": {"graph.dimensions": ["date", "experiment_slug"], "graph.metrics": ["value"]},
    },
    {
        "name": "Latest lift summary",
        "sql": f"""WITH latest AS (
  SELECT r.experiment_id, r.metric, r.value, r.interval_lower, r.interval_upper, r.result_date,
         ROW_NUMBER() OVER (PARTITION BY r.experiment_id, r.metric ORDER BY r.result_date DESC) AS rn
  FROM public.experiment_results r
)
SELECT e.experiment_slug, e.experiment_type, l.metric, l.value, l.interval_lower, l.interval_upper, l.result_date
FROM latest l
JOIN public.experiments e ON e.id = l.experiment_id
WHERE l.rn = 1 AND e.{_CF}
ORDER BY e.experiment_slug""",
        "display": "table",
        "viz": {},
    },
]

# Dashboard 2: Channel Performance
CHANNEL_PERFORMANCE_QUESTIONS = [
    {
        "name": "Spend by channel over time",
        "sql": f"SELECT report_date AS date, channel, COALESCE(SUM(spend), 0) AS spend FROM public_marts.fact_spend_daily WHERE {_CF} GROUP BY report_date, channel ORDER BY report_date, channel",
        "display": "line",
        "viz": {"graph.dimensions": ["date", "channel"], "graph.metrics": ["spend"]},
    },
    {
        "name": "ROAS by channel",
        "sql": f"""SELECT s.channel,
  COALESCE(SUM(s.spend), 0) AS spend,
  (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily WHERE {_CF}) AS revenue,
  CASE WHEN SUM(s.spend) = 0 THEN 0 ELSE (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily WHERE {_CF}) / NULLIF(SUM(s.spend), 0) END AS roas
FROM public_marts.fact_spend_daily s
WHERE s.{_CF}
GROUP BY s.channel
ORDER BY spend DESC""",
        "display": "table",
        "viz": {},
    },
    {
        "name": "Impressions and clicks by channel",
        "sql": f"SELECT report_date AS date, channel, SUM(impressions) AS impressions, SUM(clicks) AS clicks FROM public_marts.fact_spend_daily WHERE {_CF} GROUP BY report_date, channel ORDER BY report_date, channel",
        "display": "line",
        "viz": {"graph.dimensions": ["date", "channel"], "graph.metrics": ["impressions", "clicks"]},
    },
    {
        "name": "Spend share by channel",
        "sql": f"SELECT channel, COALESCE(SUM(spend), 0) AS spend FROM public_marts.fact_spend_daily WHERE {_CF} GROUP BY channel ORDER BY spend DESC",
        "display": "pie",
        "viz": {"pie.dimension": "channel", "pie.metric": "spend"},
    },
]


def _create_dashboard_with_cards(
    headers: dict,
    db_id: int,
    dashboard_name: str,
    questions: list[dict],
    existing_names: set[str],
) -> bool:
    if dashboard_name in existing_names:
        print(f"Dashboard already exists: {dashboard_name} (skipping)")
        return True
    dash = create_dashboard(headers, dashboard_name)
    if not dash:
        return False
    dashboard_id = dash["id"]
    print(f"Created dashboard: {dashboard_name} (id={dashboard_id})")
    col, row = 0, 0
    for q in questions:
        card = create_card(
            headers,
            db_id,
            name=q["name"],
            sql=q["sql"],
            display=q["display"],
            viz_settings=q.get("viz"),
        )
        if card:
            add_card_to_dashboard(headers, dashboard_id, card["id"], row=row, col=col, size_x=8, size_y=4)
            print(f"  Added card: {q['name']} (id={card['id']})")
            col += 8
            if col >= 16:
                col, row = 0, row + 4
        else:
            print(f"  Skipped: {q['name']}")
    print(f"  -> {METABASE_URL}/dashboard/{dashboard_id}\n")
    return True


def _parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Create MVP dashboards in Metabase")
    parser.add_argument("--client", help="Client slug — prefixes dashboard names (e.g. 'acme' → 'acme — Executive Overview')")
    parser.add_argument("--database-id", type=int, help="Metabase database id to use (skip auto-detect)")
    parser.add_argument("--database-name", help="Metabase database name to use (e.g. 'measurement-acme')")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    db_id = get_database_id(headers, database_id=args.database_id, database_name=args.database_name)
    if not db_id:
        print("No database found. Add your Supabase DB in Metabase first.", file=sys.stderr)
        return 1
    print(f"Using database id: {db_id}\n")

    prefix = f"{args.client} — " if args.client else ""

    dashboards = list_dashboards(headers)
    existing_names = {d.get("name") for d in dashboards if d.get("name")}

    _create_dashboard_with_cards(
        headers, db_id, f"{prefix}Executive Overview", EXEC_OVERVIEW_QUESTIONS, existing_names
    )
    _create_dashboard_with_cards(
        headers, db_id, f"{prefix}Channel Performance", CHANNEL_PERFORMANCE_QUESTIONS, existing_names
    )
    _create_dashboard_with_cards(
        headers, db_id, f"{prefix}Email & Klaviyo", EMAIL_KLAVIYO_QUESTIONS, existing_names
    )
    _create_dashboard_with_cards(
        headers, db_id, f"{prefix}Experiment Results", EXPERIMENT_RESULTS_QUESTIONS, existing_names
    )

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
