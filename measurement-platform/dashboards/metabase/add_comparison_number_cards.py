#!/usr/bin/env python3
"""
Add Number cards with period-over-period comparison to Channel Performance dashboard.

Each card shows:
- Current period value (large number)
- % change vs comparison period (with indicator)

Uses 4 date filters: Start date, End date, Comparison start date, Comparison end date

Run with same env as create_mvp_dashboards.py:
  METABASE_URL, METABASE_EMAIL, METABASE_PASSWORD (or METABASE_API_KEY)
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
from create_mvp_dashboards import (
    add_card_to_dashboard,
    get_database_id,
    get_headers,
    list_dashboards,
    login,
    METABASE_URL,
)

# Date filter variables (required - must set filter values)
_P1 = "{{report_date_start}}::date"
_P2 = "{{report_date_end}}::date"
_C1 = "{{comparison_date_start}}::date"
_C2 = "{{comparison_date_end}}::date"

# Number cards with comparison
NUMBER_CARDS = [
    {
        "name": "Total Spend",
        "main_field": "spend",
        "sql": f"""
WITH current_period AS (
  SELECT COALESCE(SUM(spend), 0) AS value
  FROM public_marts.fact_spend_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
),
comparison_period AS (
  SELECT COALESCE(SUM(spend), 0) AS value
  FROM public_marts.fact_spend_daily
  WHERE report_date >= {_C1} AND report_date <= {_C2}
)
SELECT
  ROUND(c.value::numeric, 2) AS spend,
  CASE WHEN p.value = 0 THEN 0
       ELSE ROUND(((c.value - p.value) / p.value * 100)::numeric, 1)
  END AS change_pct
FROM current_period c, comparison_period p
""",
        "display": "scalar",
    },
    {
        "name": "Total Impressions",
        "main_field": "impressions",
        "sql": f"""
WITH current_period AS (
  SELECT COALESCE(SUM(impressions), 0) AS value
  FROM public_marts.fact_spend_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
),
comparison_period AS (
  SELECT COALESCE(SUM(impressions), 0) AS value
  FROM public_marts.fact_spend_daily
  WHERE report_date >= {_C1} AND report_date <= {_C2}
)
SELECT
  c.value::bigint AS impressions,
  CASE WHEN p.value = 0 THEN 0
       ELSE ROUND(((c.value - p.value) / p.value * 100)::numeric, 1)
  END AS change_pct
FROM current_period c, comparison_period p
""",
        "display": "scalar",
    },
    {
        "name": "Total Clicks",
        "main_field": "clicks",
        "sql": f"""
WITH current_period AS (
  SELECT COALESCE(SUM(clicks), 0) AS value
  FROM public_marts.fact_spend_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
),
comparison_period AS (
  SELECT COALESCE(SUM(clicks), 0) AS value
  FROM public_marts.fact_spend_daily
  WHERE report_date >= {_C1} AND report_date <= {_C2}
)
SELECT
  c.value::bigint AS clicks,
  CASE WHEN p.value = 0 THEN 0
       ELSE ROUND(((c.value - p.value) / p.value * 100)::numeric, 1)
  END AS change_pct
FROM current_period c, comparison_period p
""",
        "display": "scalar",
    },
    {
        "name": "ROAS",
        "main_field": "roas",
        "sql": f"""
WITH current_revenue AS (
  SELECT COALESCE(SUM(revenue), 0) AS value
  FROM public_marts.fact_kpi_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
),
current_spend AS (
  SELECT COALESCE(SUM(spend), 0) AS value
  FROM public_marts.fact_spend_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
),
comparison_revenue AS (
  SELECT COALESCE(SUM(revenue), 0) AS value
  FROM public_marts.fact_kpi_daily
  WHERE report_date >= {_C1} AND report_date <= {_C2}
),
comparison_spend AS (
  SELECT COALESCE(SUM(spend), 0) AS value
  FROM public_marts.fact_spend_daily
  WHERE report_date >= {_C1} AND report_date <= {_C2}
)
SELECT
  ROUND((CASE WHEN cs.value = 0 THEN 0 ELSE cr.value / NULLIF(cs.value, 0) END)::numeric, 2) AS roas,
  CASE WHEN ps.value = 0 OR pr.value = 0 THEN 0
       ELSE ROUND((((cr.value / NULLIF(cs.value, 0)) - (pr.value / NULLIF(ps.value, 0)))
                   / NULLIF((pr.value / NULLIF(ps.value, 0)), 0) * 100)::numeric, 1)
  END AS change_pct
FROM current_revenue cr, current_spend cs, comparison_revenue pr, comparison_spend ps
""",
        "display": "scalar",
    },
]


def build_template_tags() -> dict:
    """Four date variables for period comparison."""
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
        "comparison_date_start": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "comparison_date_start",
            "display-name": "Comparison start date",
            "type": "date",
        },
        "comparison_date_end": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "comparison_date_end",
            "display-name": "Comparison end date",
            "type": "date",
        },
    }


def create_card_with_variable(
    headers: dict,
    database_id: int,
    name: str,
    sql: str,
    template_tags: dict,
    display: str = "scalar",
    main_field: str = "current_value",
) -> dict | None:
    """Create a Number card with date variables."""
    payload = {
        "name": name,
        "database_id": database_id,
        "dataset_query": {
            "type": "native",
            "database": database_id,
            "native": {
                "query": sql,
                "template-tags": template_tags,
            },
        },
        "display": display,
        "visualization_settings": {
            "scalar.field": main_field,
        },
    }
    r = requests.post(f"{METABASE_URL}/api/card", json=payload, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        print(f"Create card '{name}' failed: {r.status_code} {r.text[:300]}", file=sys.stderr)
        return None
    return r.json()


def get_dashboard_by_name(headers: dict, name: str) -> dict | None:
    """Get dashboard by name with full details."""
    dashboards = list_dashboards(headers)
    for d in dashboards:
        if d.get("name") == name:
            dash_id = d.get("id")
            if dash_id:
                r = requests.get(f"{METABASE_URL}/api/dashboard/{dash_id}", headers=headers, timeout=30)
                if r.status_code == 200:
                    return r.json()
            return d
    return None


def main() -> int:
    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    db_id = get_database_id(headers)
    if not db_id:
        print("No database found. Add your Supabase DB in Metabase first.", file=sys.stderr)
        return 1

    dash = get_dashboard_by_name(headers, "Channel Performance")
    if not dash:
        print("Channel Performance dashboard not found.", file=sys.stderr)
        return 1

    dashboard_id = dash["id"]
    dashcards = dash.get("dashcards", [])
    max_row = max((dc.get("row", 0) + dc.get("size_y", 4) for dc in dashcards), default=0)

    template_tags = build_template_tags()

    print(f"Adding Number cards to Channel Performance (id={dashboard_id})...")
    col = 0
    for card_def in NUMBER_CARDS:
        card = create_card_with_variable(
            headers,
            db_id,
            card_def["name"],
            card_def["sql"],
            template_tags,
            display=card_def["display"],
            main_field=card_def.get("main_field", "current_value"),
        )
        if card:
            add_card_to_dashboard(
                headers, dashboard_id, card["id"],
                row=max_row, col=col, size_x=6, size_y=4
            )
            print(f"  Added: {card_def['name']} (id={card['id']})")
            col += 6
            if col >= 12:
                col = 0
                max_row += 4
        else:
            print(f"  Failed: {card_def['name']}")

    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard_id}")
    print("\nNumber cards added. Each shows:")
    print("  - Main value (large number)")
    print("  - change_pct available in the query (visible when you click into the card)")
    print("\nNote: Metabase doesn't natively show % in the corner like Shopify.")
    print("The main value is displayed large. Click a card to see the % change.")
    print("\nIMPORTANT: You must set all 4 date filters for the cards to work:")
    print("  - Start date, End date (primary period)")
    print("  - Comparison start date, Comparison end date (comparison period)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
