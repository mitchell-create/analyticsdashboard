#!/usr/bin/env python3
"""
Comprehensive fix for all executive metric cards.
Fixes blank queries, SQL syntax errors, and ensures cards show totals.
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


def restore_card(headers: dict, card_id: int, db_id: int, sql: str) -> bool:
    """Restore/fix a card with complete query structure."""
    card = get_card(headers, card_id)
    if not card:
        print(f"  Card {card_id} not found")
        return False

    # Build complete dataset_query structure - this is critical
    card["dataset_query"] = {
        "type": "native",
        "native": {
            "query": sql.strip(),
            "template-tags": {}
        },
        "database": db_id
    }
    
    # Set display to scalar for totals
    card["display"] = "scalar"
    card["visualization_settings"] = {}

    # Update the card
    r = requests.put(f"{METABASE_URL}/api/card/{card_id}", json=card, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        print(f"  Failed: {r.status_code} {r.text[:300]}")
        return False
    return True


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
    print(f"Using database id: {db_id}")
    print("Fixing all executive metric cards...\n")

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
        
        # Fix all Executive cards
        if "Executive" in card_name:
            print(f"Fixing: {card_name} (id={card_id})")
            
            # Check if query is blank or has errors
            dataset_query = card.get("dataset_query", {})
            is_blank = not dataset_query or dataset_query == {}
            
            if is_blank or "Orders" in card_name:
                sql = """
SELECT SUM(orders) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
                if restore_card(headers, card_id, db_id, sql):
                    print(f"  ✓ Fixed: {card_name}")
                    updated += 1
                continue

            if is_blank or "Revenue" in card_name:
                sql = """
SELECT SUM(revenue) AS total_revenue
FROM public_marts.fact_kpi_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
                if restore_card(headers, card_id, db_id, sql):
                    print(f"  ✓ Fixed: {card_name}")
                    updated += 1
                continue

            if is_blank or "Spend" in card_name:
                sql = """
SELECT SUM(spend) AS total_spend
FROM public_marts.fact_spend_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
                if restore_card(headers, card_id, db_id, sql):
                    print(f"  ✓ Fixed: {card_name}")
                    updated += 1
                continue

            if is_blank or "Impressions" in card_name:
                sql = """
SELECT SUM(impressions) AS total_impressions
FROM public_marts.fact_spend_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
                if restore_card(headers, card_id, db_id, sql):
                    print(f"  ✓ Fixed: {card_name}")
                    updated += 1
                continue

            if is_blank or "Clicks" in card_name:
                sql = """
SELECT SUM(clicks) AS total_clicks
FROM public_marts.fact_spend_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
                if restore_card(headers, card_id, db_id, sql):
                    print(f"  ✓ Fixed: {card_name}")
                    updated += 1
                continue

    print(f"\n✓ Fixed {updated} executive metric cards")
    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard['id']}")
    print("\nAll cards now show total values (SUM) for the date range.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
