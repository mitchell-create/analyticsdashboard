#!/usr/bin/env python3
"""
Create Metabase "Executive Overview - Comparison" dashboard with period-over-period % change.
Uses {{period_days}} variable (default 7) for "last N days vs previous N days".

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
    create_card,
    create_dashboard,
    get_database_id,
    get_headers,
    list_dashboards,
    login,
    METABASE_URL,
)

# SQL returns: metric, current, prior, pct_change
# Uses {{period_days}} - e.g. 7 for "last 7 days vs previous 7 days"
COMPARISON_SQL = """
WITH kpi AS (
  SELECT
    SUM(CASE WHEN report_date >= CURRENT_DATE - ({{period_days}} * INTERVAL '1 day') AND report_date < CURRENT_DATE THEN revenue ELSE 0 END) as cur_revenue,
    SUM(CASE WHEN report_date >= CURRENT_DATE - ({{period_days}} * 2 * INTERVAL '1 day') AND report_date < CURRENT_DATE - ({{period_days}} * INTERVAL '1 day') THEN revenue ELSE 0 END) as prior_revenue,
    SUM(CASE WHEN report_date >= CURRENT_DATE - ({{period_days}} * INTERVAL '1 day') AND report_date < CURRENT_DATE THEN orders ELSE 0 END) as cur_orders,
    SUM(CASE WHEN report_date >= CURRENT_DATE - ({{period_days}} * 2 * INTERVAL '1 day') AND report_date < CURRENT_DATE - ({{period_days}} * INTERVAL '1 day') THEN orders ELSE 0 END) as prior_orders
  FROM public_marts.fact_kpi_daily
  WHERE report_date >= CURRENT_DATE - ({{period_days}} * 2 * INTERVAL '1 day') AND report_date < CURRENT_DATE
),
spend AS (
  SELECT
    SUM(CASE WHEN report_date >= CURRENT_DATE - ({{period_days}} * INTERVAL '1 day') AND report_date < CURRENT_DATE THEN spend ELSE 0 END) as cur_spend,
    SUM(CASE WHEN report_date >= CURRENT_DATE - ({{period_days}} * 2 * INTERVAL '1 day') AND report_date < CURRENT_DATE - ({{period_days}} * INTERVAL '1 day') THEN spend ELSE 0 END) as prior_spend,
    SUM(CASE WHEN report_date >= CURRENT_DATE - ({{period_days}} * INTERVAL '1 day') AND report_date < CURRENT_DATE THEN impressions ELSE 0 END) as cur_impressions,
    SUM(CASE WHEN report_date >= CURRENT_DATE - ({{period_days}} * 2 * INTERVAL '1 day') AND report_date < CURRENT_DATE - ({{period_days}} * INTERVAL '1 day') THEN impressions ELSE 0 END) as prior_impressions,
    SUM(CASE WHEN report_date >= CURRENT_DATE - ({{period_days}} * INTERVAL '1 day') AND report_date < CURRENT_DATE THEN clicks ELSE 0 END) as cur_clicks,
    SUM(CASE WHEN report_date >= CURRENT_DATE - ({{period_days}} * 2 * INTERVAL '1 day') AND report_date < CURRENT_DATE - ({{period_days}} * INTERVAL '1 day') THEN clicks ELSE 0 END) as prior_clicks
  FROM public_marts.fact_spend_daily
  WHERE report_date >= CURRENT_DATE - ({{period_days}} * 2 * INTERVAL '1 day') AND report_date < CURRENT_DATE
)
SELECT 'Revenue' as metric, k.cur_revenue as current, k.prior_revenue as prior,
  CASE WHEN k.prior_revenue = 0 THEN 0 ELSE ROUND(((k.cur_revenue - k.prior_revenue) / k.prior_revenue * 100)::numeric, 1) END as pct_change
FROM kpi k
UNION ALL
SELECT 'Orders', k.cur_orders::numeric, k.prior_orders::numeric,
  CASE WHEN k.prior_orders = 0 THEN 0 ELSE ROUND(((k.cur_orders - k.prior_orders)::numeric / k.prior_orders * 100), 1) END
FROM kpi k
UNION ALL
SELECT 'Spend', s.cur_spend, s.prior_spend,
  CASE WHEN s.prior_spend = 0 THEN 0 ELSE ROUND(((s.cur_spend - s.prior_spend) / s.prior_spend * 100)::numeric, 1) END
FROM spend s
UNION ALL
SELECT 'ROAS',
  CASE WHEN s.cur_spend = 0 THEN 0 ELSE k.cur_revenue / s.cur_spend END,
  CASE WHEN s.prior_spend = 0 THEN 0 ELSE k.prior_revenue / s.prior_spend END,
  CASE WHEN s.prior_spend = 0 OR k.prior_revenue = 0 THEN 0
       ELSE ROUND((((k.cur_revenue / NULLIF(s.cur_spend, 0)) - (k.prior_revenue / NULLIF(s.prior_spend, 0))) / (k.prior_revenue / NULLIF(s.prior_spend, 0)) * 100)::numeric, 1) END
FROM kpi k, spend s
UNION ALL
SELECT 'Impressions', s.cur_impressions::numeric, s.prior_impressions::numeric,
  CASE WHEN s.prior_impressions = 0 THEN 0 ELSE ROUND(((s.cur_impressions - s.prior_impressions)::numeric / s.prior_impressions * 100), 1) END
FROM spend s
UNION ALL
SELECT 'Clicks', s.cur_clicks::numeric, s.prior_clicks::numeric,
  CASE WHEN s.prior_clicks = 0 THEN 0 ELSE ROUND(((s.cur_clicks - s.prior_clicks)::numeric / s.prior_clicks * 100), 1) END
FROM spend s
ORDER BY metric
"""


def create_card_with_variable(
    headers: dict,
    database_id: int,
    name: str,
    sql: str,
    template_tags: dict,
    display: str = "table",
    viz_settings: dict | None = None,
) -> dict | None:
    """Create a card with template-tags (variables)."""
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
        print("No database found. Add your Supabase DB in Metabase first.", file=sys.stderr)
        return 1

    dashboards = list_dashboards(headers)
    existing_names = {d.get("name") for d in dashboards if d.get("name")}

    dashboard_name = "Executive Overview - Comparison"
    if dashboard_name in existing_names:
        print(f"Dashboard '{dashboard_name}' already exists. Skipping creation.")
        print("To recreate, delete the dashboard in Metabase first.")
        return 0

    dash = create_dashboard(headers, dashboard_name)
    if not dash:
        return 1
    dashboard_id = dash["id"]
    print(f"Created dashboard: {dashboard_name} (id={dashboard_id})")

    template_tags = {
        "period_days": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "period_days",
            "display-name": "Period (days)",
            "type": "number",
            "default": 7,
        },
    }

    card = create_card_with_variable(
        headers,
        db_id,
        "Key metrics: Current vs Prior period",
        COMPARISON_SQL,
        template_tags,
        display="table",
        viz_settings={},
    )
    if card:
        add_card_to_dashboard(headers, dashboard_id, card["id"], row=0, col=0, size_x=12, size_y=6)
        print(f"  Added card: Key metrics: Current vs Prior period (id={card['id']})")

    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard_id}")
    print("\nAdd a dashboard filter: Number type, label 'Period (days)', link to 'period_days'.")
    print("Use 7, 14, or 30 for different period lengths.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
