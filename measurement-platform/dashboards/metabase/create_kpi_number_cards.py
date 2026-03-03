#!/usr/bin/env python3
"""
Create KPI number cards with configurable comparison period.

Each card uses Metabase's smartscalar (Trend) display:
  - Shows a large number for the selected date range
  - Shows up/down arrow with % change vs the comparison period

Comparison modes (set via the "Compare to" dashboard filter):
  previous_period  — same # of days immediately before start date (default)
  previous_year    — same date range one year earlier

Example with Start=Feb 10, End=Feb 26 (17 days):
  previous_period  -> compares to Jan 24 - Feb 9, 2026
  previous_year    -> compares to Feb 10 - Feb 26, 2025

Dashboard filters needed:
  Start date       (required)
  End date         (required)
  Compare to       (optional — defaults to previous_period)

PowerShell usage:
  cd "C:\\...\\measurement-platform\\dashboards\\metabase"
  $env:METABASE_EMAIL = "you@example.com"
  $env:METABASE_PASSWORD = "password"
  python create_kpi_number_cards.py
  python create_kpi_number_cards.py --dashboard "Executive Overview"
"""
from __future__ import annotations

import argparse
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
    create_dashboard,
    get_database_id,
    get_headers,
    list_dashboards,
    login,
    METABASE_URL,
)

# ---------------------------------------------------------------------------
# Shared SQL fragments
# ---------------------------------------------------------------------------
# The params + comp CTEs compute the comparison date range based on
# the compare_mode variable.  Every card's SQL starts with these CTEs.

_PARAMS_CTE = """
WITH params AS (
  SELECT {{report_date_start}}::date AS s,
         {{report_date_end}}::date   AS e,
         ({{report_date_end}}::date - {{report_date_start}}::date + 1) AS days,
         {{compare_mode}} AS cmp
),
comp AS (
  SELECT
    CASE WHEN cmp = 'previous_year'
         THEN (s - INTERVAL '1 year')::date
         ELSE s - days
    END AS cs,
    CASE WHEN cmp = 'previous_year'
         THEN (e - INTERVAL '1 year')::date
         ELSE s - 1
    END AS ce
  FROM params
)"""

# WHERE helpers (reference the CTEs above)
_W_CURR = "client_slug = {{client_slug}} AND report_date >= (SELECT s FROM params) AND report_date <= (SELECT e FROM params)"
_W_COMP = "client_slug = {{client_slug}} AND report_date >= (SELECT cs FROM comp) AND report_date <= (SELECT ce FROM comp)"


# ---------------------------------------------------------------------------
# SQL builders
# ---------------------------------------------------------------------------

def _simple_kpi_sql(metric_col: str, agg: str, table: str) -> str:
    """KPI from a single table (e.g. SUM(spend) from fact_spend_daily)."""
    return f"""{_PARAMS_CTE}
SELECT (SELECT ce FROM comp) AS date,
       COALESCE({agg}, 0) AS {metric_col}
FROM {table}
WHERE {_W_COMP}
UNION ALL
SELECT (SELECT e FROM params) AS date,
       COALESCE({agg}, 0) AS {metric_col}
FROM {table}
WHERE {_W_CURR}
ORDER BY date
"""


def _ratio_kpi_sql(
    metric_col: str,
    num_agg: str, num_table: str,
    den_agg: str, den_table: str,
) -> str:
    """KPI ratio across two tables (e.g. ROAS = revenue / spend)."""
    return f"""{_PARAMS_CTE}
SELECT (SELECT ce FROM comp) AS date,
       ROUND(COALESCE(
         (SELECT {num_agg} FROM {num_table} WHERE {_W_COMP})
         / NULLIF(
           (SELECT {den_agg} FROM {den_table} WHERE {_W_COMP}), 0),
         0)::numeric, 2) AS {metric_col}
UNION ALL
SELECT (SELECT e FROM params) AS date,
       ROUND(COALESCE(
         (SELECT {num_agg} FROM {num_table} WHERE {_W_CURR})
         / NULLIF(
           (SELECT {den_agg} FROM {den_table} WHERE {_W_CURR}), 0),
         0)::numeric, 2) AS {metric_col}
ORDER BY date
"""


def _comparison_chart_sql(metric_col: str, agg: str, table: str) -> str:
    """Line chart overlaying current vs comparison period on same date axis."""
    return f"""{_PARAMS_CTE}
SELECT 'Current Period' AS period, report_date AS date,
       COALESCE({agg}, 0) AS {metric_col}
FROM {table}
WHERE {_W_CURR}
GROUP BY report_date
UNION ALL
SELECT 'Previous Period' AS period,
       (report_date + ((SELECT s FROM params) - (SELECT cs FROM comp)))::date AS date,
       COALESCE({agg}, 0) AS {metric_col}
FROM {table}
WHERE {_W_COMP}
GROUP BY report_date, ((SELECT s FROM params) - (SELECT cs FROM comp))
ORDER BY date, period
"""


# ---------------------------------------------------------------------------
# Card definitions
# ---------------------------------------------------------------------------
KPI_NUMBER_CARDS: list[dict] = [
    {
        "name": "KPI: Total Spend",
        "metric_col": "total_spend",
        "sql": _simple_kpi_sql("total_spend", "SUM(spend)", "public_marts.fact_spend_daily"),
    },
    {
        "name": "KPI: Total Revenue",
        "metric_col": "total_revenue",
        "sql": _simple_kpi_sql("total_revenue", "SUM(revenue)", "public_marts.fact_kpi_daily"),
    },
    {
        "name": "KPI: ROAS",
        "metric_col": "roas",
        "sql": _ratio_kpi_sql(
            "roas",
            "SUM(revenue)", "public_marts.fact_kpi_daily",
            "SUM(spend)", "public_marts.fact_spend_daily",
        ),
    },
    {
        "name": "KPI: Total Orders",
        "metric_col": "total_orders",
        "sql": _simple_kpi_sql("total_orders", "SUM(orders)", "public_marts.fact_kpi_daily"),
    },
    {
        "name": "KPI: CPA",
        "metric_col": "cpa",
        "sql": _ratio_kpi_sql(
            "cpa",
            "SUM(spend)", "public_marts.fact_spend_daily",
            "SUM(orders)", "public_marts.fact_kpi_daily",
        ),
    },
    {
        "name": "KPI: AOV",
        "metric_col": "aov",
        "sql": _ratio_kpi_sql(
            "aov",
            "SUM(revenue)", "public_marts.fact_kpi_daily",
            "SUM(orders)", "public_marts.fact_kpi_daily",
        ),
    },
]

COMPARISON_CHARTS: list[dict] = [
    {
        "name": "Spend: Current vs Previous Period",
        "display": "line",
        "viz": {"graph.dimensions": ["date", "period"], "graph.metrics": ["spend"]},
        "sql": _comparison_chart_sql("spend", "SUM(spend)", "public_marts.fact_spend_daily"),
    },
    {
        "name": "Revenue: Current vs Previous Period",
        "display": "line",
        "viz": {"graph.dimensions": ["date", "period"], "graph.metrics": ["revenue"]},
        "sql": _comparison_chart_sql("revenue", "SUM(revenue)", "public_marts.fact_kpi_daily"),
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_template_tags() -> dict:
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
        "compare_mode": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "compare_mode",
            "display-name": "Compare to",
            "type": "text",
            "default": "previous_period",
        },
        "client_slug": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "client_slug",
            "display-name": "Client",
            "type": "text",
            "default": "default",
        },
    }


def create_card_with_vars(
    headers: dict,
    database_id: int,
    name: str,
    sql: str,
    template_tags: dict,
    display: str = "smartscalar",
    viz_settings: dict | None = None,
) -> dict | None:
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
        "visualization_settings": viz_settings or {},
    }
    r = requests.post(
        f"{METABASE_URL}/api/card", json=payload, headers=headers, timeout=30,
    )
    if r.status_code not in (200, 201):
        print(f"Create card '{name}' failed: {r.status_code} {r.text[:300]}", file=sys.stderr)
        return None
    return r.json()


def get_or_create_dashboard(headers: dict, name: str, existing_names: set[str]) -> dict | None:
    if name in existing_names:
        for d in list_dashboards(headers):
            if d.get("name") == name:
                dash_id = d.get("id")
                if dash_id:
                    r = requests.get(f"{METABASE_URL}/api/dashboard/{dash_id}", headers=headers, timeout=30)
                    if r.status_code == 200:
                        return r.json()
                return d
        return None
    return create_dashboard(headers, name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Create KPI number cards with comparison")
    parser.add_argument("--dashboard", default="KPI Summary",
                        help='Target dashboard name (default: "KPI Summary")')
    parser.add_argument("--client", help="Client slug — prefixes dashboard name (e.g. 'acme' → 'acme — KPI Summary')")
    parser.add_argument("--database-id", type=int, help="Metabase database id (skip auto-detect)")
    parser.add_argument("--database-name", help="Metabase database name (e.g. 'measurement-acme')")
    args = parser.parse_args()

    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    db_id = get_database_id(headers, database_id=args.database_id, database_name=args.database_name)
    if not db_id:
        print("No database found. Add your Supabase DB in Metabase first.", file=sys.stderr)
        return 1

    if args.client:
        args.dashboard = f"{args.client} — {args.dashboard}"

    dashboards = list_dashboards(headers)
    existing_names = {d.get("name") for d in dashboards if d.get("name")}

    dash = get_or_create_dashboard(headers, args.dashboard, existing_names)
    if not dash:
        print(f"Could not find or create dashboard '{args.dashboard}'.", file=sys.stderr)
        return 1

    dashboard_id = dash["id"]
    dashcards = dash.get("dashcards", [])
    max_row = max((dc.get("row", 0) + dc.get("size_y", 4) for dc in dashcards), default=0)

    template_tags = build_template_tags()

    # --- KPI Number Cards ---
    print(f"Adding KPI number cards to '{args.dashboard}' (id={dashboard_id})...\n")
    col = 0
    for card_def in KPI_NUMBER_CARDS:
        card = create_card_with_vars(headers, db_id, card_def["name"], card_def["sql"],
                                     template_tags, display="smartscalar")
        if card:
            add_card_to_dashboard(headers, dashboard_id, card["id"],
                                  row=max_row, col=col, size_x=4, size_y=3)
            print(f"  + {card_def['name']} (id={card['id']})")
            col += 4
            if col >= 12:
                col = 0
                max_row += 3
        else:
            print(f"  FAILED: {card_def['name']}")

    if col > 0:
        max_row += 3
        col = 0

    # --- Comparison Line Charts ---
    print("\nAdding comparison line charts...\n")
    for chart_def in COMPARISON_CHARTS:
        card = create_card_with_vars(headers, db_id, chart_def["name"], chart_def["sql"],
                                     template_tags, display=chart_def["display"],
                                     viz_settings=chart_def.get("viz"))
        if card:
            add_card_to_dashboard(headers, dashboard_id, card["id"],
                                  row=max_row, col=col, size_x=6, size_y=4)
            print(f"  + {chart_def['name']} (id={card['id']})")
            col += 6
            if col >= 12:
                col = 0
                max_row += 4
        else:
            print(f"  FAILED: {chart_def['name']}")

    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard_id}")
    print("""
Done! Now add 3 dashboard filters:

  1. Start date      -> wire to "report_date_start" on all cards
  2. End date        -> wire to "report_date_end" on all cards
  3. Compare to      -> wire to "compare_mode" on all cards
                        (Text/Category filter — type one of:)
                          previous_period   (default — prior N days)
                          previous_year     (same dates last year)

If you don't add the "Compare to" filter, it defaults to previous_period.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
