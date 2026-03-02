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

Usage:
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


def _period_days_expr() -> str:
    return f"({_P2} - {_P1} + 1)"


def _prev_start() -> str:
    """Expression for the first day of the previous period."""
    return f"({_P1} - {_period_days_expr()})"


# ---------------------------------------------------------------------------
# KPI Number Cards (smartscalar — 2 rows: prev aggregate, then current)
# ---------------------------------------------------------------------------
KPI_NUMBER_CARDS: list[dict] = [
    {
        "name": "KPI: Total Spend",
        "metric_col": "total_spend",
        "sql": f"""
WITH params AS (
  SELECT {_P1} AS range_start, {_P2} AS range_end,
         {_period_days_expr()} AS period_days
)
SELECT (SELECT range_start - 1 FROM params) AS date,
       COALESCE(SUM(spend), 0) AS total_spend
FROM public_marts.fact_spend_daily
WHERE report_date >= (SELECT range_start - period_days FROM params)
  AND report_date <  (SELECT range_start FROM params)
UNION ALL
SELECT (SELECT range_end FROM params) AS date,
       COALESCE(SUM(spend), 0) AS total_spend
FROM public_marts.fact_spend_daily
WHERE report_date >= (SELECT range_start FROM params)
  AND report_date <= (SELECT range_end FROM params)
ORDER BY date
""",
    },
    {
        "name": "KPI: Total Revenue",
        "metric_col": "total_revenue",
        "sql": f"""
WITH params AS (
  SELECT {_P1} AS range_start, {_P2} AS range_end,
         {_period_days_expr()} AS period_days
)
SELECT (SELECT range_start - 1 FROM params) AS date,
       COALESCE(SUM(revenue), 0) AS total_revenue
FROM public_marts.fact_kpi_daily
WHERE report_date >= (SELECT range_start - period_days FROM params)
  AND report_date <  (SELECT range_start FROM params)
UNION ALL
SELECT (SELECT range_end FROM params) AS date,
       COALESCE(SUM(revenue), 0) AS total_revenue
FROM public_marts.fact_kpi_daily
WHERE report_date >= (SELECT range_start FROM params)
  AND report_date <= (SELECT range_end FROM params)
ORDER BY date
""",
    },
    {
        "name": "KPI: ROAS",
        "metric_col": "roas",
        "sql": f"""
WITH params AS (
  SELECT {_P1} AS range_start, {_P2} AS range_end,
         {_period_days_expr()} AS period_days
)
SELECT (SELECT range_start - 1 FROM params) AS date,
       ROUND(COALESCE(
         (SELECT SUM(revenue) FROM public_marts.fact_kpi_daily
          WHERE report_date >= (SELECT range_start - period_days FROM params)
            AND report_date <  (SELECT range_start FROM params))
         / NULLIF(
           (SELECT SUM(spend) FROM public_marts.fact_spend_daily
            WHERE report_date >= (SELECT range_start - period_days FROM params)
              AND report_date <  (SELECT range_start FROM params)), 0),
         0)::numeric, 2) AS roas
UNION ALL
SELECT (SELECT range_end FROM params) AS date,
       ROUND(COALESCE(
         (SELECT SUM(revenue) FROM public_marts.fact_kpi_daily
          WHERE report_date >= (SELECT range_start FROM params)
            AND report_date <= (SELECT range_end FROM params))
         / NULLIF(
           (SELECT SUM(spend) FROM public_marts.fact_spend_daily
            WHERE report_date >= (SELECT range_start FROM params)
              AND report_date <= (SELECT range_end FROM params)), 0),
         0)::numeric, 2) AS roas
ORDER BY date
""",
    },
    {
        "name": "KPI: Total Orders",
        "metric_col": "total_orders",
        "sql": f"""
WITH params AS (
  SELECT {_P1} AS range_start, {_P2} AS range_end,
         {_period_days_expr()} AS period_days
)
SELECT (SELECT range_start - 1 FROM params) AS date,
       COALESCE(SUM(orders), 0) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE report_date >= (SELECT range_start - period_days FROM params)
  AND report_date <  (SELECT range_start FROM params)
UNION ALL
SELECT (SELECT range_end FROM params) AS date,
       COALESCE(SUM(orders), 0) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE report_date >= (SELECT range_start FROM params)
  AND report_date <= (SELECT range_end FROM params)
ORDER BY date
""",
    },
    {
        "name": "KPI: CPA",
        "metric_col": "cpa",
        "sql": f"""
WITH params AS (
  SELECT {_P1} AS range_start, {_P2} AS range_end,
         {_period_days_expr()} AS period_days
)
SELECT (SELECT range_start - 1 FROM params) AS date,
       ROUND(COALESCE(
         (SELECT SUM(spend) FROM public_marts.fact_spend_daily
          WHERE report_date >= (SELECT range_start - period_days FROM params)
            AND report_date <  (SELECT range_start FROM params))
         / NULLIF(
           (SELECT SUM(orders) FROM public_marts.fact_kpi_daily
            WHERE report_date >= (SELECT range_start - period_days FROM params)
              AND report_date <  (SELECT range_start FROM params)), 0),
         0)::numeric, 2) AS cpa
UNION ALL
SELECT (SELECT range_end FROM params) AS date,
       ROUND(COALESCE(
         (SELECT SUM(spend) FROM public_marts.fact_spend_daily
          WHERE report_date >= (SELECT range_start FROM params)
            AND report_date <= (SELECT range_end FROM params))
         / NULLIF(
           (SELECT SUM(orders) FROM public_marts.fact_kpi_daily
            WHERE report_date >= (SELECT range_start FROM params)
              AND report_date <= (SELECT range_end FROM params)), 0),
         0)::numeric, 2) AS cpa
ORDER BY date
""",
    },
    {
        "name": "KPI: AOV",
        "metric_col": "aov",
        "sql": f"""
WITH params AS (
  SELECT {_P1} AS range_start, {_P2} AS range_end,
         {_period_days_expr()} AS period_days
)
SELECT (SELECT range_start - 1 FROM params) AS date,
       ROUND(COALESCE(
         (SELECT SUM(revenue) FROM public_marts.fact_kpi_daily
          WHERE report_date >= (SELECT range_start - period_days FROM params)
            AND report_date <  (SELECT range_start FROM params))
         / NULLIF(
           (SELECT SUM(orders) FROM public_marts.fact_kpi_daily
            WHERE report_date >= (SELECT range_start - period_days FROM params)
              AND report_date <  (SELECT range_start FROM params)), 0),
         0)::numeric, 2) AS aov
UNION ALL
SELECT (SELECT range_end FROM params) AS date,
       ROUND(COALESCE(
         (SELECT SUM(revenue) FROM public_marts.fact_kpi_daily
          WHERE report_date >= (SELECT range_start FROM params)
            AND report_date <= (SELECT range_end FROM params))
         / NULLIF(
           (SELECT SUM(orders) FROM public_marts.fact_kpi_daily
            WHERE report_date >= (SELECT range_start FROM params)
              AND report_date <= (SELECT range_end FROM params)), 0),
         0)::numeric, 2) AS aov
ORDER BY date
""",
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
WITH params AS (
  SELECT {_P1} AS range_start, {_P2} AS range_end,
         {_period_days_expr()} AS period_days
)
SELECT 'Current Period' AS period, report_date AS date,
       COALESCE(SUM(spend), 0) AS spend
FROM public_marts.fact_spend_daily
WHERE report_date >= (SELECT range_start FROM params)
  AND report_date <= (SELECT range_end FROM params)
GROUP BY report_date
UNION ALL
SELECT 'Previous Period' AS period,
       (report_date + (SELECT period_days FROM params))::date AS date,
       COALESCE(SUM(spend), 0) AS spend
FROM public_marts.fact_spend_daily
WHERE report_date >= (SELECT range_start - period_days FROM params)
  AND report_date <  (SELECT range_start FROM params)
GROUP BY report_date, (SELECT period_days FROM params)
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
WITH params AS (
  SELECT {_P1} AS range_start, {_P2} AS range_end,
         {_period_days_expr()} AS period_days
)
SELECT 'Current Period' AS period, report_date AS date,
       COALESCE(SUM(revenue), 0) AS revenue
FROM public_marts.fact_kpi_daily
WHERE report_date >= (SELECT range_start FROM params)
  AND report_date <= (SELECT range_end FROM params)
GROUP BY report_date
UNION ALL
SELECT 'Previous Period' AS period,
       (report_date + (SELECT period_days FROM params))::date AS date,
       COALESCE(SUM(revenue), 0) AS revenue
FROM public_marts.fact_kpi_daily
WHERE report_date >= (SELECT range_start - period_days FROM params)
  AND report_date <  (SELECT range_start FROM params)
GROUP BY report_date, (SELECT period_days FROM params)
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

    # --- KPI Number Cards (smartscalar) ---
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
            print(f"  ✓ {card_def['name']} (id={card['id']})")
            col += 4
            if col >= 12:
                col = 0
                max_row += 3
        else:
            print(f"  ✗ {card_def['name']} — FAILED")

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
            print(f"  ✓ {chart_def['name']} (id={card['id']})")
            col += 6
            if col >= 12:
                col = 0
                max_row += 4
        else:
            print(f"  ✗ {chart_def['name']} — FAILED")

    print(f"\n  → {METABASE_URL}/dashboard/{dashboard_id}")
    print(
        "\nDone! Each KPI card shows a big number with ↑/↓ % change arrow.\n"
        "\nNext steps:\n"
        "  1. Open the dashboard in Metabase.\n"
        "  2. Click the pencil icon (Edit) → Filter icon → add 2 filters:\n"
        "     • Date picker → Single date → name it 'Start date'\n"
        "     • Date picker → Single date → name it 'End date'\n"
        "  3. For each filter, click the gear icon and connect it to every card:\n"
        "     • Start date  →  report_date_start\n"
        "     • End date    →  report_date_end\n"
        "  4. Save the dashboard.\n"
        "  5. Set the filters (e.g. Start: Feb 10, End: Feb 26) and the cards\n"
        "     will show the aggregated KPI with comparison vs the prior period.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
