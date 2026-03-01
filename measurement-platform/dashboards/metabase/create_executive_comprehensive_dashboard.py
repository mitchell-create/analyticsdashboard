#!/usr/bin/env python3
"""
Create comprehensive Executive Overview dashboard with KPI scorecards.

Includes:
- Row 1: Total Spend, Revenue, MER, Net Profit
- Row 2: Orders, CPA, AOV, CAC
- Row 3: New Customers, Returning Customers, LTV, LTV:CAC
- Row 4: Daily Spend vs Revenue (line chart)
- Row 5: Spend Share by Platform (pie chart)
- Row 6: Impressions, Clicks, CPC, CPM, CVR

Uses date range filters: Start date, End date

Run with: METABASE_URL, METABASE_EMAIL, METABASE_PASSWORD
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
    create_dashboard,
    get_database_id,
    get_headers,
    list_dashboards,
    login,
    METABASE_URL,
)

# Date filters
_P1 = "{{report_date_start}}::date"
_P2 = "{{report_date_end}}::date"

# Row 1: Executive KPIs (using Trend visualization)
CARDS_ROW1 = [
    {
        "name": "Total Ad Spend",
        "sql": f"SELECT COALESCE(SUM(spend), 0) AS total_spend FROM public_marts.fact_spend_daily WHERE report_date >= {_P1} AND report_date <= {_P2}",
        "display": "trend",
    },
    {
        "name": "Total Shopify Revenue",
        "sql": f"SELECT COALESCE(SUM(revenue), 0) AS total_revenue FROM public_marts.fact_kpi_daily WHERE report_date >= {_P1} AND report_date <= {_P2}",
        "display": "trend",
    },
    {
        "name": "MER (Marketing Efficiency Ratio)",
        "sql": f"""
SELECT ROUND((COALESCE(SUM(k.revenue), 0) / NULLIF(COALESCE(SUM(s.spend), 0), 0))::numeric, 2) AS mer
FROM public_marts.fact_kpi_daily k, public_marts.fact_spend_daily s
WHERE k.report_date >= {_P1} AND k.report_date <= {_P2}
  AND s.report_date >= {_P1} AND s.report_date <= {_P2}
""",
        "display": "trend",
    },
    {
        "name": "Net Ad Profit",
        "sql": f"""
SELECT COALESCE(SUM(k.revenue), 0) - COALESCE(SUM(s.spend), 0) AS net_profit
FROM public_marts.fact_kpi_daily k, public_marts.fact_spend_daily s
WHERE k.report_date >= {_P1} AND k.report_date <= {_P2}
  AND s.report_date >= {_P1} AND s.report_date <= {_P2}
""",
        "display": "trend",
    },
]

# Row 2: Efficiency KPIs (using Trend visualization)
CARDS_ROW2 = [
    {
        "name": "Total Shopify Orders",
        "sql": f"SELECT COALESCE(SUM(orders), 0) AS total_orders FROM public_marts.fact_kpi_daily WHERE report_date >= {_P1} AND report_date <= {_P2}",
        "display": "trend",
    },
    {
        "name": "CPA (Cost Per Purchase)",
        "sql": f"""
SELECT ROUND((COALESCE(SUM(s.spend), 0) / NULLIF(COALESCE(SUM(k.orders), 0), 0))::numeric, 2) AS cpa
FROM public_marts.fact_spend_daily s, public_marts.fact_spend_daily k
WHERE s.report_date >= {_P1} AND s.report_date <= {_P2}
""",
        "display": "trend",
    },
    {
        "name": "AOV (Average Order Value)",
        "sql": f"""
SELECT ROUND((COALESCE(SUM(revenue), 0) / NULLIF(COALESCE(SUM(orders), 0), 0))::numeric, 2) AS aov
FROM public_marts.fact_kpi_daily
WHERE report_date >= {_P1} AND report_date <= {_P2}
""",
        "display": "trend",
    },
    {
        "name": "Blended CAC",
        "sql": f"""
SELECT ROUND((COALESCE(SUM(s.spend), 0) / NULLIF(COALESCE(SUM(k.orders), 0), 0))::numeric, 2) AS cac
FROM public_marts.fact_spend_daily s, public_marts.fact_kpi_daily k
WHERE s.report_date >= {_P1} AND s.report_date <= {_P2}
  AND k.report_date >= {_P1} AND k.report_date <= {_P2}
""",
        "display": "trend",
    },
]

# Row 3: Customer KPIs
CARDS_ROW3 = [
    {
        "name": "New Customers",
        "sql": f"SELECT 0 AS new_customers",  # Placeholder - need customer data
        "display": "scalar",
    },
    {
        "name": "Returning Customers",
        "sql": f"SELECT 0 AS returning_customers",  # Placeholder
        "display": "scalar",
    },
    {
        "name": "LTV (Lifetime Value)",
        "sql": f"SELECT 0.00 AS ltv",  # Placeholder
        "display": "scalar",
    },
    {
        "name": "LTV:CAC Ratio",
        "sql": f"SELECT 0.00 AS ltv_cac",  # Placeholder
        "display": "scalar",
    },
]

# Row 4: Main trend chart
CHART_DAILY_SPEND_REVENUE = {
    "name": "Daily Spend vs Revenue",
    "sql": f"""
SELECT
  k.report_date AS date,
  COALESCE(SUM(s.spend), 0) AS spend,
  COALESCE(SUM(k.revenue), 0) AS revenue
FROM public_marts.fact_kpi_daily k
LEFT JOIN public_marts.fact_spend_daily s ON k.report_date = s.report_date
WHERE k.report_date >= {_P1} AND k.report_date <= {_P2}
GROUP BY k.report_date
ORDER BY k.report_date
""",
    "display": "line",
    "viz": {"graph.dimensions": ["date"], "graph.metrics": ["spend", "revenue"]},
}

# Row 5: Spend share pie chart
CHART_SPEND_SHARE = {
    "name": "Spend Share by Platform",
    "sql": f"""
SELECT channel, COALESCE(SUM(spend), 0) AS spend
FROM public_marts.fact_spend_daily
WHERE report_date >= {_P1} AND report_date <= {_P2}
GROUP BY channel
ORDER BY spend DESC
""",
    "display": "pie",
    "viz": {"pie.dimension": "channel", "pie.metric": "spend"},
}

# Row 6: Supporting diagnostic metrics (using Trend visualization)
CARDS_ROW6 = [
    {
        "name": "Total Impressions",
        "sql": f"SELECT COALESCE(SUM(impressions), 0) AS impressions FROM public_marts.fact_spend_daily WHERE report_date >= {_P1} AND report_date <= {_P2}",
        "display": "trend",
    },
    {
        "name": "Total Clicks",
        "sql": f"SELECT COALESCE(SUM(clicks), 0) AS clicks FROM public_marts.fact_spend_daily WHERE report_date >= {_P1} AND report_date <= {_P2}",
        "display": "trend",
    },
    {
        "name": "Blended CPC",
        "sql": f"""
SELECT ROUND((COALESCE(SUM(spend), 0) / NULLIF(COALESCE(SUM(clicks), 0), 0))::numeric, 2) AS cpc
FROM public_marts.fact_spend_daily
WHERE report_date >= {_P1} AND report_date <= {_P2}
""",
        "display": "trend",
    },
    {
        "name": "Blended CPM",
        "sql": f"""
SELECT ROUND(((COALESCE(SUM(spend), 0) / NULLIF(COALESCE(SUM(impressions), 0), 0)) * 1000)::numeric, 2) AS cpm
FROM public_marts.fact_spend_daily
WHERE report_date >= {_P1} AND report_date <= {_P2}
""",
        "display": "trend",
    },
    {
        "name": "CVR (Conversion Rate)",
        "sql": f"""
SELECT ROUND(((COALESCE(SUM(k.orders), 0)::numeric / NULLIF(COALESCE(SUM(s.clicks), 0), 0)) * 100), 2) AS cvr_pct
FROM public_marts.fact_kpi_daily k, public_marts.fact_spend_daily s
WHERE k.report_date >= {_P1} AND k.report_date <= {_P2}
  AND s.report_date >= {_P1} AND s.report_date <= {_P2}
""",
        "display": "trend",
    },
]


def build_template_tags() -> dict:
    """Two date variables for date range."""
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


def create_card_with_variable(
    headers: dict,
    database_id: int,
    name: str,
    sql: str,
    template_tags: dict,
    display: str = "scalar",
    viz_settings: dict | None = None,
) -> dict | None:
    """Create a card with date variables."""
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
    r = requests.post(f"{METABASE_URL}/api/card", json=payload, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        print(f"Create card '{name}' failed: {r.status_code} {r.text[:300]}", file=sys.stderr)
        return None
    return r.json()


def main() -> int:
    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    db_id = get_database_id(headers)
    if not db_id:
        print("No database found.", file=sys.stderr)
        return 1

    dashboards = list_dashboards(headers)
    existing_names = {d.get("name") for d in dashboards if d.get("name")}

    dashboard_name = "Executive Overview - Comprehensive"
    if dashboard_name in existing_names:
        print(f"Dashboard '{dashboard_name}' already exists. Delete it first to recreate.")
        return 0

    dash = create_dashboard(headers, dashboard_name)
    if not dash:
        return 1
    dashboard_id = dash["id"]
    print(f"Created dashboard: {dashboard_name} (id={dashboard_id})")

    template_tags = build_template_tags()
    row = 0

    # Row 1: Executive KPIs (4 cards, 3 cols each = 12 total)
    print("\nRow 1: Executive KPIs")
    col = 0
    for card_def in CARDS_ROW1:
        card = create_card_with_variable(
            headers, db_id, card_def["name"], card_def["sql"],
            template_tags, display=card_def["display"]
        )
        if card:
            add_card_to_dashboard(headers, dashboard_id, card["id"], row=row, col=col, size_x=3, size_y=3)
            print(f"  Added: {card_def['name']}")
            col += 3
    row += 3

    # Row 2: Efficiency KPIs
    print("\nRow 2: Efficiency KPIs")
    col = 0
    for card_def in CARDS_ROW2:
        card = create_card_with_variable(
            headers, db_id, card_def["name"], card_def["sql"],
            template_tags, display=card_def["display"]
        )
        if card:
            add_card_to_dashboard(headers, dashboard_id, card["id"], row=row, col=col, size_x=3, size_y=3)
            print(f"  Added: {card_def['name']}")
            col += 3
    row += 3

    # Row 3: Customer KPIs
    print("\nRow 3: Customer KPIs (placeholders for now)")
    col = 0
    for card_def in CARDS_ROW3:
        card = create_card_with_variable(
            headers, db_id, card_def["name"], card_def["sql"],
            template_tags, display=card_def["display"]
        )
        if card:
            add_card_to_dashboard(headers, dashboard_id, card["id"], row=row, col=col, size_x=3, size_y=3)
            print(f"  Added: {card_def['name']} (placeholder)")
            col += 3
    row += 3

    # Row 4: Daily Spend vs Revenue chart
    print("\nRow 4: Daily Spend vs Revenue")
    card = create_card_with_variable(
        headers, db_id, CHART_DAILY_SPEND_REVENUE["name"], CHART_DAILY_SPEND_REVENUE["sql"],
        template_tags, display=CHART_DAILY_SPEND_REVENUE["display"],
        viz_settings=CHART_DAILY_SPEND_REVENUE["viz"]
    )
    if card:
        add_card_to_dashboard(headers, dashboard_id, card["id"], row=row, col=0, size_x=12, size_y=4)
        print(f"  Added: {CHART_DAILY_SPEND_REVENUE['name']}")
    row += 4

    # Row 5: Spend Share pie chart
    print("\nRow 5: Spend Share by Platform")
    card = create_card_with_variable(
        headers, db_id, CHART_SPEND_SHARE["name"], CHART_SPEND_SHARE["sql"],
        template_tags, display=CHART_SPEND_SHARE["display"],
        viz_settings=CHART_SPEND_SHARE["viz"]
    )
    if card:
        add_card_to_dashboard(headers, dashboard_id, card["id"], row=row, col=0, size_x=12, size_y=4)
        print(f"  Added: {CHART_SPEND_SHARE['name']}")
    row += 4

    # Row 6: Supporting diagnostic metrics (5 cards, smaller)
    print("\nRow 6: Supporting Metrics")
    col = 0
    for card_def in CARDS_ROW6:
        card = create_card_with_variable(
            headers, db_id, card_def["name"], card_def["sql"],
            template_tags, display=card_def["display"]
        )
        if card:
            size_x = 2 if len(CARDS_ROW6) == 5 else 3  # Fit 5 cards across 12 cols
            add_card_to_dashboard(headers, dashboard_id, card["id"], row=row, col=col, size_x=size_x, size_y=3)
            print(f"  Added: {card_def['name']}")
            col += size_x
            if col >= 12:
                col = 0
                row += 3

    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard_id}")
    print("\nDashboard created with Trend visualization for all Number cards.")
    print("Add Start date and End date filters and link them to all cards.")
    print("\nTrend cards show the current value. To see comparison/trends:")
    print("  - Metabase may auto-calculate trends if you have time-series data")
    print("  - Or manually compare by changing the date filters")
    print("\nNote: New Customers, Returning Customers, LTV, and LTV:CAC are placeholders (show 0).")
    print("Update those SQL queries when customer cohort data is available.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
