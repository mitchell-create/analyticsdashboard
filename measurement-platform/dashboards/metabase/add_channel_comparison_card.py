#!/usr/bin/env python3
"""
Add a period-over-period comparison card to the existing Channel Performance dashboard.

The card shows each channel's metrics (spend, ROAS, impressions, clicks) for the current
period vs the prior period with % change. Uses {{period_days}} variable (e.g. 7 = last 7 days vs previous 7 days).

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

# Channel-level comparison: current vs prior period with % change (spend, impressions, clicks)
CHANNEL_COMPARISON_SQL = """
WITH cur AS (
  SELECT channel,
    SUM(spend) AS spend,
    SUM(impressions) AS impressions,
    SUM(clicks) AS clicks
  FROM public_marts.fact_spend_daily
  WHERE report_date >= CURRENT_DATE - ({{period_days}} * INTERVAL '1 day')
    AND report_date < CURRENT_DATE
  GROUP BY channel
),
prior AS (
  SELECT channel,
    SUM(spend) AS spend,
    SUM(impressions) AS impressions,
    SUM(clicks) AS clicks
  FROM public_marts.fact_spend_daily
  WHERE report_date >= CURRENT_DATE - ({{period_days}} * 2 * INTERVAL '1 day')
    AND report_date < CURRENT_DATE - ({{period_days}} * INTERVAL '1 day')
  GROUP BY channel
)
SELECT
  COALESCE(c.channel, p.channel) AS channel,
  COALESCE(c.spend, 0) AS cur_spend,
  COALESCE(p.spend, 0) AS prior_spend,
  CASE WHEN COALESCE(p.spend, 0) = 0 THEN 0
       ELSE ROUND(((COALESCE(c.spend, 0) - COALESCE(p.spend, 0)) / p.spend * 100)::numeric, 1) END AS spend_pct_change,
  COALESCE(c.impressions, 0) AS cur_impressions,
  COALESCE(p.impressions, 0) AS prior_impressions,
  CASE WHEN COALESCE(p.impressions, 0) = 0 THEN 0
       ELSE ROUND(((COALESCE(c.impressions, 0) - COALESCE(p.impressions, 0)) / p.impressions * 100)::numeric, 1) END AS impressions_pct_change,
  COALESCE(c.clicks, 0) AS cur_clicks,
  COALESCE(p.clicks, 0) AS prior_clicks,
  CASE WHEN COALESCE(p.clicks, 0) = 0 THEN 0
       ELSE ROUND(((COALESCE(c.clicks, 0) - COALESCE(p.clicks, 0)) / p.clicks * 100)::numeric, 1) END AS clicks_pct_change
FROM cur c
FULL OUTER JOIN prior p ON c.channel = p.channel
ORDER BY cur_spend DESC NULLS LAST
"""


def create_card_with_variable(
    headers: dict,
    database_id: int,
    name: str,
    sql: str,
    template_tags: dict,
    display: str = "table",
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
        "visualization_settings": {},
    }
    r = requests.post(f"{METABASE_URL}/api/card", json=payload, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        print(f"Create card '{name}' failed: {r.status_code} {r.text[:300]}", file=sys.stderr)
        return None
    return r.json()


def get_dashboard_by_name(headers: dict, name: str) -> dict | None:
    """Get dashboard by name, with full details including dashcards."""
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
        print("Channel Performance dashboard not found. Create it first with create_mvp_dashboards.py.", file=sys.stderr)
        return 1

    dashboard_id = dash["id"]
    dashcards = dash.get("dashcards", [])

    # Check if comparison card already exists on this dashboard
    card_name = "Channel comparison: Current vs Prior period"
    for dc in dashcards:
        card = dc.get("card") or {}
        if card.get("name") == card_name:
            print(f"Card '{card_name}' already exists on Channel Performance. Skipping.")
            print(f"\nAdd a Period (days) filter: Number type, Equal to, Single value, default 7.")
            print(f"Link it to the card's period_days variable.")
            return 0

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
        card_name,
        CHANNEL_COMPARISON_SQL,
        template_tags,
        display="table",
    )
    if not card:
        return 1

    # Add at bottom - find max row and add below
    max_row = max((dc.get("row", 0) + (dc.get("size_y") or 4) for dc in dashcards), default=0)
    add_card_to_dashboard(
        headers, dashboard_id, card["id"],
        row=max_row, col=0, size_x=12, size_y=6
    )

    print(f"Added '{card_name}' to Channel Performance (id={card['id']})")
    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard_id}")
    print("\nNext: Add a Period (days) filter to the dashboard:")
    print("  1. Edit dashboard → + Add a filter → Number")
    print("  2. Label: Period (days), Operator: Equal to, People can pick: A single value, Default: 7")
    print("  3. Link the filter to this card's period_days variable")
    print("\nUse 7, 14, or 30 for different period lengths (e.g. 7 = last 7 days vs previous 7 days).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
