#!/usr/bin/env python3
"""
Create KPI number cards with automatic previous-period comparison.

Each card uses Metabase's smartscalar (Trend) display:
  - Shows a large number for the selected date range
  - Shows ↑/↓ arrow with % change vs the previous period

The previous period is auto-computed as the same number of days
immediately before start_date.  Example:
  Start: Feb 10, End: Feb 26  →  17-day period
  Previous period: Jan 24 – Feb 9  (also 17 days)

Only 2 dashboard date filters needed: Start date, End date.
NO previous-period date filter needed — it's automatic.

Also creates comparison line charts that overlay current vs previous
period on the same date axis.

Cards created:
  KPI: Total Spend       KPI: Total Revenue
  KPI: ROAS              KPI: Total Orders
  KPI: CPA               KPI: AOV
  Spend: Current vs Previous Period   (line chart)
  Revenue: Current vs Previous Period (line chart)

Run with same env as create_mvp_dashboards.py:
  METABASE_URL, METABASE_EMAIL, METABASE_PASSWORD (or METABASE_API_KEY)

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
# Template-tag date variables
# ---------------------------------------------------------------------------
_P1 = "{{report_date_start}}::date"
_P2 = "{{report_date_end}}::date"
_DAYS = f"({_P2} - {_P1} + 1)"

# Reusable WHERE fragments
_CURR = f"""report_date >= {_P1} AND report_date <= {_P2}"""
_PREV = f"""report_date >= ({_P1} - {_DAYS}) AND report_date < {_P1}"""


# ---------------------------------------------------------------------------
# SQL builders — each returns 2 rows (prev, curr) for smartscalar display.
# Metabase Trend shows the latest row as the big number and computes
# ↑/↓ % change vs the previous row.
# ---------------------------------------------------------------------------

def _simple_kpi_sql(metric_col: str, agg: str, table: str) -> str:
    """KPI from a single table (e.g. SUM(spend) from fact_spend_daily)."""
    return f"""
SELECT ({_P1} - 1) AS date,
       COALESCE({agg}, 0) AS {metric_col}
FROM {table}
WHERE {_PREV}
UNION ALL
SELECT {_P2} AS date,
       COALESCE({agg}, 0) AS {metric_col}
FROM {table}
WHERE {_CURR}
ORDER BY date
"""


def _ratio_kpi_sql(
    metric_col: str,
    num_agg: str, num_table: str,
    den_agg: str, den_table: str,
) -> str:
    """KPI that is a ratio across two tables (e.g. ROAS = revenue/spend)."""
    return f"""
SELECT ({_P1} - 1) AS date,
       ROUND(COALESCE(
         (SELECT {num_agg} FROM {num_table} WHERE {_PREV})
         / NULLIF(
           (SELECT {den_agg} FROM {den_table} WHERE {_PREV}), 0),
         0)::numeric, 2) AS {metric_col}
UNION ALL
SELECT {_P2} AS date,
       ROUND(COALESCE(
         (SELECT {num_agg} FROM {num_table} WHERE {_CURR})
         / NULLIF(
           (SELECT {den_agg} FROM {den_table} WHERE {_CURR}), 0),
         0)::numeric, 2) AS {metric_col}
ORDER BY date
"""


# ---------------------------------------------------------------------------
# KPI Number Cards (smartscalar / Trend display)
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

# ---------------------------------------------------------------------------
# Comparison Line Charts (overlay current vs previous on same date axis)
# ---------------------------------------------------------------------------
COMPARISON_CHARTS: list[dict] = [
    {
        "name": "Spend: Current vs Previous Period",
        "display": "line",
        "viz": {
            "graph.dimensions": ["date", "period"],
            "graph.metrics": ["spend"],
        },
        "sql": f"""
SELECT 'Current Period' AS period, report_date AS date,
       COALESCE(SUM(spend), 0) AS spend
FROM public_marts.fact_spend_daily
WHERE {_CURR}
GROUP BY report_date
UNION ALL
SELECT 'Previous Period' AS period,
       (report_date + {_DAYS})::date AS date,
       COALESCE(SUM(spend), 0) AS spend
FROM public_marts.fact_spend_daily
WHERE {_PREV}
GROUP BY report_date, {_DAYS}
ORDER BY date, period
""",
    },
    {
        "name": "Revenue: Current vs Previous Period",
        "display": "line",
        "viz": {
            "graph.dimensions": ["date", "period"],
            "graph.metrics": ["revenue"],
        },
        "sql": f"""
SELECT 'Current Period' AS period, report_date AS date,
       COALESCE(SUM(revenue), 0) AS revenue
FROM public_marts.fact_kpi_daily
WHERE {_CURR}
GROUP BY report_date
UNION ALL
SELECT 'Previous Period' AS period,
       (report_date + {_DAYS})::date AS date,
       COALESCE(SUM(revenue), 0) AS revenue
FROM public_marts.fact_kpi_daily
WHERE {_PREV}
GROUP BY report_date, {_DAYS}
ORDER BY date, period
""",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_template_tags() -> dict:
    """Two date variables: Start date + End date."""
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
        f"{METABASE_URL}/api/card",
        json=payload,
        headers=headers,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        print(
            f"Create card '{name}' failed: {r.status_code} {r.text[:300]}",
            file=sys.stderr,
        )
        return None
    return r.json()


def get_or_create_dashboard(
    headers: dict,
    name: str,
    existing_names: set[str],
) -> dict | None:
    if name in existing_names:
        dashboards = list_dashboards(headers)
        for d in dashboards:
            if d.get("name") == name:
                dash_id = d.get("id")
                if dash_id:
                    r = requests.get(
                        f"{METABASE_URL}/api/dashboard/{dash_id}",
                        headers=headers,
                        timeout=30,
                    )
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
    parser.add_argument(
        "--dashboard",
        default="KPI Summary",
        help='Target dashboard name (default: "KPI Summary")',
    )
    args = parser.parse_args()

    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    db_id = get_database_id(headers)
    if not db_id:
        print("No database found. Add your Supabase DB in Metabase first.", file=sys.stderr)
        return 1

    dashboards = list_dashboards(headers)
    existing_names = {d.get("name") for d in dashboards if d.get("name")}

    dash = get_or_create_dashboard(headers, args.dashboard, existing_names)
    if not dash:
        print(f"Could not find or create dashboard '{args.dashboard}'.", file=sys.stderr)
        return 1

    dashboard_id = dash["id"]
    dashcards = dash.get("dashcards", [])
    max_row = max(
        (dc.get("row", 0) + dc.get("size_y", 4) for dc in dashcards),
        default=0,
    )

    template_tags = build_template_tags()

    # --- KPI Number Cards (smartscalar / Trend) ---
    print(f"Adding KPI number cards to '{args.dashboard}' (id={dashboard_id})...\n")
    col = 0
    for card_def in KPI_NUMBER_CARDS:
        card = create_card_with_vars(
            headers,
            db_id,
            card_def["name"],
            card_def["sql"],
            template_tags,
            display="smartscalar",
        )
        if card:
            add_card_to_dashboard(
                headers, dashboard_id, card["id"],
                row=max_row, col=col, size_x=4, size_y=3,
            )
            print(f"  \u2713 {card_def['name']} (id={card['id']})")
            col += 4
            if col >= 12:
                col = 0
                max_row += 3
        else:
            print(f"  \u2717 {card_def['name']} \u2014 FAILED")

    if col > 0:
        max_row += 3
        col = 0

    # --- Comparison Line Charts ---
    print("\nAdding comparison line charts...\n")
    for chart_def in COMPARISON_CHARTS:
        card = create_card_with_vars(
            headers,
            db_id,
            chart_def["name"],
            chart_def["sql"],
            template_tags,
            display=chart_def["display"],
            viz_settings=chart_def.get("viz"),
        )
        if card:
            add_card_to_dashboard(
                headers, dashboard_id, card["id"],
                row=max_row, col=col, size_x=6, size_y=4,
            )
            print(f"  \u2713 {chart_def['name']} (id={card['id']})")
            col += 6
            if col >= 12:
                col = 0
                max_row += 4
        else:
            print(f"  \u2717 {chart_def['name']} \u2014 FAILED")

    print(f"\n  \u2192 {METABASE_URL}/dashboard/{dashboard_id}")
    print(
        "\nDone! Each KPI card shows a big number with comparison arrow.\n"
        "\nNote: Metabase labels the comparison 'vs. previous day' but the\n"
        "VALUES are correct full-period aggregates. See KPI_NUMBER_CARDS_SETUP.md\n"
        "for how to rename the comparison label in each card.\n"
        "\nReminder: You only need 2 date filters (Start date + End date).\n"
        "The previous period is calculated automatically.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
