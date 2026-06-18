#!/usr/bin/env python3
"""
Add Shopify-style KPI comparison cards to a Metabase dashboard.

What this creates:
- Trend cards that show a headline KPI value plus up/down % change
- Comparison modes controlled by a dashboard text/category filter:
  - previous_period (default): same-length window immediately before the selected range
  - previous_month: selected range shifted back 1 month
  - previous_quarter: selected range shifted back 3 months
  - previous_year: selected range shifted back 1 year

Required dashboard filters (link manually in Metabase):
- Start date -> report_date_start
- End date -> report_date_end
- Comparison mode -> comparison_mode

Run with same env as other scripts:
  METABASE_URL, METABASE_EMAIL, METABASE_PASSWORD (or METABASE_API_KEY)

Optional:
  METABASE_TARGET_DASHBOARD (default: "Executive Overview")
"""
from __future__ import annotations

import os
import sys
import uuid

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from create_mvp_dashboards import (  # noqa: E402
    METABASE_URL,
    add_card_to_dashboard,
    get_database_id,
    get_headers,
    list_dashboards,
    login,
)

TARGET_DASHBOARD = os.environ.get("METABASE_TARGET_DASHBOARD", "Executive Overview")


def build_template_tags() -> dict:
    """Template tags shared by all cards."""
    return {
        "report_date_start": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "report_date_start",
            "display-name": "Start date",
            "type": "date",
        },
        "report_date_end": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "report_date_end",
            "display-name": "End date",
            "type": "date",
        },
        "comparison_mode": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "comparison_mode",
            "display-name": "Comparison mode",
            "type": "text",
            "default": "previous_period",
        },
    }


_RANGE_CTE = """
WITH params AS (
  SELECT
    {{report_date_start}}::date AS start_date,
    {{report_date_end}}::date AS end_date,
    LOWER(COALESCE(NULLIF({{comparison_mode}}, ''), 'previous_period')) AS comparison_mode
),
ranges AS (
  SELECT
    start_date,
    end_date,
    comparison_mode,
    ((end_date - start_date) + 1)::int AS days_in_period,
    CASE
      WHEN comparison_mode = 'previous_year' THEN (start_date - INTERVAL '1 year')::date
      WHEN comparison_mode = 'previous_quarter' THEN (start_date - INTERVAL '3 months')::date
      WHEN comparison_mode = 'previous_month' THEN (start_date - INTERVAL '1 month')::date
      ELSE (start_date - (((end_date - start_date) + 1)::int * INTERVAL '1 day'))::date
    END AS compare_start,
    CASE
      WHEN comparison_mode = 'previous_year' THEN (end_date - INTERVAL '1 year')::date
      WHEN comparison_mode = 'previous_quarter' THEN (end_date - INTERVAL '3 months')::date
      WHEN comparison_mode = 'previous_month' THEN (end_date - INTERVAL '1 month')::date
      ELSE (start_date - INTERVAL '1 day')::date
    END AS compare_end
  FROM params
)
"""


def build_sum_metric_sql(table_name: str, metric_expr: str) -> str:
    """Two-point trend: comparison point + current point."""
    return (
        _RANGE_CTE
        + f""",
cur AS (
  SELECT COALESCE(SUM({metric_expr}), 0)::numeric AS value
  FROM {table_name} t
  CROSS JOIN ranges r
  WHERE t.report_date >= r.start_date AND t.report_date <= r.end_date
),
cmp AS (
  SELECT COALESCE(SUM({metric_expr}), 0)::numeric AS value
  FROM {table_name} t
  CROSS JOIN ranges r
  WHERE t.report_date >= r.compare_start AND t.report_date <= r.compare_end
)
SELECT (r.end_date - INTERVAL '1 day')::date AS date, cmp.value AS value
FROM ranges r
CROSS JOIN cmp
UNION ALL
SELECT r.end_date::date AS date, cur.value AS value
FROM ranges r
CROSS JOIN cur
ORDER BY date
"""
    )


def build_roas_sql() -> str:
    """ROAS trend: current ROAS vs comparison ROAS."""
    return (
        _RANGE_CTE
        + """
,cur AS (
  SELECT
    CASE
      WHEN COALESCE(SUM(s.spend), 0) = 0 THEN 0::numeric
      ELSE (COALESCE(SUM(k.revenue), 0) / NULLIF(COALESCE(SUM(s.spend), 0), 0))::numeric
    END AS value
  FROM ranges r
  LEFT JOIN public_marts.fact_kpi_daily k
    ON k.report_date >= r.start_date AND k.report_date <= r.end_date
  LEFT JOIN public_marts.fact_spend_daily s
    ON s.report_date >= r.start_date AND s.report_date <= r.end_date
),
cmp AS (
  SELECT
    CASE
      WHEN COALESCE(SUM(s.spend), 0) = 0 THEN 0::numeric
      ELSE (COALESCE(SUM(k.revenue), 0) / NULLIF(COALESCE(SUM(s.spend), 0), 0))::numeric
    END AS value
  FROM ranges r
  LEFT JOIN public_marts.fact_kpi_daily k
    ON k.report_date >= r.compare_start AND k.report_date <= r.compare_end
  LEFT JOIN public_marts.fact_spend_daily s
    ON s.report_date >= r.compare_start AND s.report_date <= r.compare_end
)
SELECT (r.end_date - INTERVAL '1 day')::date AS date, cmp.value AS value
FROM ranges r
CROSS JOIN cmp
UNION ALL
SELECT r.end_date::date AS date, cur.value AS value
FROM ranges r
CROSS JOIN cur
ORDER BY date
"""
    )


KPI_CARD_DEFS = [
    {
        "name": "KPI Revenue - Comparison",
        "sql": build_sum_metric_sql("public_marts.fact_kpi_daily", "revenue"),
    },
    {
        "name": "KPI Orders - Comparison",
        "sql": build_sum_metric_sql("public_marts.fact_kpi_daily", "orders"),
    },
    {
        "name": "KPI Spend - Comparison",
        "sql": build_sum_metric_sql("public_marts.fact_spend_daily", "spend"),
    },
    {
        "name": "KPI ROAS - Comparison",
        "sql": build_roas_sql(),
    },
    {
        "name": "KPI Clicks - Comparison",
        "sql": build_sum_metric_sql("public_marts.fact_spend_daily", "clicks"),
    },
    {
        "name": "KPI Impressions - Comparison",
        "sql": build_sum_metric_sql("public_marts.fact_spend_daily", "impressions"),
    },
]


def list_cards(headers: dict) -> list[dict]:
    r = requests.get(f"{METABASE_URL}/api/card", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"GET /api/card failed: {r.status_code}", file=sys.stderr)
        return []
    data = r.json()
    if isinstance(data, list):
        return data
    return data.get("data", [])


def get_card(headers: dict, card_id: int) -> dict | None:
    r = requests.get(f"{METABASE_URL}/api/card/{card_id}", headers=headers, timeout=30)
    if r.status_code != 200:
        return None
    return r.json()


def get_dashboard_by_name(headers: dict, name: str) -> dict | None:
    dashboards = list_dashboards(headers)
    for d in dashboards:
        if d.get("name") == name:
            dash_id = d.get("id")
            if not dash_id:
                continue
            r = requests.get(f"{METABASE_URL}/api/dashboard/{dash_id}", headers=headers, timeout=30)
            if r.status_code != 200:
                print(f"GET /api/dashboard/{dash_id} failed: {r.status_code}", file=sys.stderr)
                return None
            return r.json()
    return None


def create_card_with_tags(
    headers: dict,
    database_id: int,
    name: str,
    sql: str,
    template_tags: dict,
) -> dict | None:
    payload = {
        "name": name,
        "database_id": database_id,
        "dataset_query": {
            "type": "native",
            "database": database_id,
            "native": {"query": sql, "template-tags": template_tags},
        },
        "display": "trend",
        "visualization_settings": {},
    }
    r = requests.post(f"{METABASE_URL}/api/card", json=payload, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        print(f"Create card '{name}' failed: {r.status_code} {r.text[:250]}", file=sys.stderr)
        return None
    return r.json()


def update_card_with_tags(
    headers: dict,
    card_id: int,
    sql: str,
    template_tags: dict,
) -> bool:
    card = get_card(headers, card_id)
    if not card:
        print(f"Could not fetch card {card_id}", file=sys.stderr)
        return False
    db_id = card.get("database_id")
    if not db_id:
        print(f"Card {card_id} missing database_id", file=sys.stderr)
        return False
    card["dataset_query"] = {
        "type": "native",
        "database": db_id,
        "native": {"query": sql, "template-tags": template_tags},
    }
    card["display"] = "trend"
    # Keep visualization settings minimal; users can tweak color direction per KPI in UI.
    card["visualization_settings"] = card.get("visualization_settings") or {}
    r = requests.put(f"{METABASE_URL}/api/card/{card_id}", json=card, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        print(f"Update card {card_id} failed: {r.status_code} {r.text[:250]}", file=sys.stderr)
        return False
    return True


def main() -> int:
    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    db_id = get_database_id(headers)
    if not db_id:
        print("No database found. Add your Supabase DB in Metabase first.", file=sys.stderr)
        return 1

    dashboard = get_dashboard_by_name(headers, TARGET_DASHBOARD)
    if not dashboard:
        print(f"Dashboard '{TARGET_DASHBOARD}' not found.", file=sys.stderr)
        return 1
    dashboard_id = dashboard["id"]
    dashcards = dashboard.get("dashcards", [])

    all_cards = list_cards(headers)
    if not all_cards:
        print("Could not list cards.", file=sys.stderr)
        return 1
    cards_by_name = {c.get("name"): c for c in all_cards if c.get("name")}

    template_tags = build_template_tags()
    existing_card_ids_on_dash = {dc.get("card_id") for dc in dashcards if dc.get("card_id")}
    max_row = max((dc.get("row", 0) + (dc.get("size_y") or 4) for dc in dashcards), default=0)

    print(f"Applying Shopify-style KPI cards to dashboard '{TARGET_DASHBOARD}' (id={dashboard_id})...")
    col = 0
    touched = 0

    for card_def in KPI_CARD_DEFS:
        name = card_def["name"]
        sql = card_def["sql"]
        existing = cards_by_name.get(name)
        card_id = None

        if existing:
            card_id = existing["id"]
            if update_card_with_tags(headers, card_id, sql, template_tags):
                print(f"Updated card: {name} (id={card_id})")
            else:
                continue
        else:
            created = create_card_with_tags(headers, db_id, name, sql, template_tags)
            if not created:
                continue
            card_id = created["id"]
            print(f"Created card: {name} (id={card_id})")

        touched += 1

        if card_id not in existing_card_ids_on_dash:
            added = add_card_to_dashboard(
                headers,
                dashboard_id,
                card_id,
                row=max_row,
                col=col,
                size_x=4,
                size_y=3,
            )
            if added:
                print(f"  Added to dashboard row={max_row}, col={col}")
                existing_card_ids_on_dash.add(card_id)
                col += 4
                if col >= 12:
                    col = 0
                    max_row += 3
            else:
                print(f"  Failed to add card {card_id} to dashboard", file=sys.stderr)

    print(f"\nDone. Touched {touched} KPI comparison card(s).")
    print("\nNext in Metabase dashboard edit mode:")
    print("1) Make sure Start date and End date filters exist and are linked to these cards.")
    print("2) Add a text/category filter labeled 'Comparison mode' and link to variable 'comparison_mode'.")
    print("3) Use one of: previous_period, previous_month, previous_quarter, previous_year.")
    print("\nTrend cards should show the latest KPI plus green/red percentage change automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
