#!/usr/bin/env python3
"""
Fix executive metric queries - remove client_slug filter since fact tables don't have it.
The fact_kpi_daily and fact_spend_daily tables are aggregated across all stores.
"""
from __future__ import annotations

import os
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from create_mvp_dashboards import (
    get_database_id,
    get_headers,
    list_dashboards,
    login,
    METABASE_URL,
)


def get_dashboard(headers: dict, dashboard_name: str) -> dict | None:
    """Get dashboard by name."""
    dashboards = list_dashboards(headers)
    for dash in dashboards:
        if dash.get("name") == dashboard_name:
            r = requests.get(f"{METABASE_URL}/api/dashboard/{dash['id']}", headers=headers, timeout=30)
            if r.status_code == 200:
                return r.json()
    return None


def get_card(headers: dict, card_id: int) -> dict | None:
    """Get card details."""
    r = requests.get(f"{METABASE_URL}/api/card/{card_id}", headers=headers, timeout=30)
    if r.status_code == 200:
        return r.json()
    return None


def fix_card(headers: dict, card_id: int, db_id: int, sql: str) -> bool:
    """Fix a card's query."""
    card = get_card(headers, card_id)
    if not card:
        return False

    card["dataset_query"] = {
        "type": "native",
        "native": {
            "query": sql.strip(),
            "template-tags": {}
        },
        "database": db_id
    }
    
    card["display"] = "scalar"
    card["visualization_settings"] = {}

    r = requests.put(f"{METABASE_URL}/api/card/{card_id}", json=card, headers=headers, timeout=30)
    return r.status_code in (200, 201)


def main() -> int:
    dashboard_name = sys.argv[1] if len(sys.argv) > 1 else "Client Performance Template v2"
    
    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    db_id = get_database_id(headers)
    if not db_id:
        print("No database found.", file=sys.stderr)
        return 1

    dashboard = get_dashboard(headers, dashboard_name)
    if not dashboard:
        print(f"Dashboard '{dashboard_name}' not found.", file=sys.stderr)
        return 1

    print(f"Found dashboard: {dashboard_name} (id={dashboard['id']})")
    print(f"Using database id: {db_id}\n")
    print("Fixing executive queries (removing client_slug filter)...\n")

    # Correct queries WITHOUT client_slug filter
    queries = {
        "Orders": """
SELECT SUM(orders) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
""",
        "Revenue": """
SELECT SUM(revenue) AS total_revenue
FROM public_marts.fact_kpi_daily
WHERE report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
""",
        "Spend": """
SELECT SUM(spend) AS total_spend
FROM public_marts.fact_spend_daily
WHERE report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
""",
        "Impressions": """
SELECT SUM(impressions) AS total_impressions
FROM public_marts.fact_spend_daily
WHERE report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
""",
        "Clicks": """
SELECT SUM(clicks) AS total_clicks
FROM public_marts.fact_spend_daily
WHERE report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
    }

    updated = 0
    dashcards = dashboard.get("dashcards", [])
    
    for dashcard in dashcards:
        card_id = dashcard.get("card_id")
        if not card_id:
            continue

        card = get_card(headers, card_id)
        if not card:
            continue

        card_name = card.get("name", "")
        
        if "Executive" not in card_name:
            continue

        print(f"Fixing: {card_name} (id={card_id})")
        
        # Match and fix
        fixed = False
        for metric, sql in queries.items():
            if metric in card_name:
                if fix_card(headers, card_id, db_id, sql):
                    print(f"  ✓ Fixed with {metric} query (no client_slug filter)")
                    updated += 1
                    fixed = True
                    break
        
        if not fixed:
            print(f"  ⚠ No matching query for: {card_name}")

    print(f"\n✓ Fixed {updated} executive metric cards")
    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard['id']}")
    print("\nQueries now aggregate across all stores (no client_slug filter).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
