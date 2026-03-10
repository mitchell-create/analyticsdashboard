#!/usr/bin/env python3
"""
Check what queries are actually in the executive cards and fix them properly.
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


def test_query(headers: dict, db_id: int, sql: str) -> tuple[bool, str, any]:
    """Test a SQL query."""
    payload = {
        "database_id": db_id,
        "query": {
            "type": "native",
            "native": {"query": sql},
        },
    }
    r = requests.post(f"{METABASE_URL}/api/dataset", json=payload, headers=headers, timeout=30)
    if r.status_code == 200:
        data = r.json()
        rows = data.get("data", {}).get("rows", [])
        return True, "Success", rows[0][0] if rows else None
    else:
        return False, f"Error {r.status_code}: {r.text[:200]}", None


def fix_card(headers: dict, card_id: int, db_id: int, sql: str) -> bool:
    """Fix a card with the correct SQL."""
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
    print("Checking and fixing executive metric cards...\n")

    # First, let's test what the correct queries should return
    print("Testing correct queries:\n")
    
    test_queries = {
        "Orders": """
SELECT SUM(orders) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
""",
        "Revenue": """
SELECT SUM(revenue) AS total_revenue
FROM public_marts.fact_kpi_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
""",
        "Spend": """
SELECT SUM(spend) AS total_spend
FROM public_marts.fact_spend_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
""",
        "Impressions": """
SELECT SUM(impressions) AS total_impressions
FROM public_marts.fact_spend_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
""",
        "Clicks": """
SELECT SUM(clicks) AS total_clicks
FROM public_marts.fact_spend_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
    }
    
    for metric, sql in test_queries.items():
        success, message, value = test_query(headers, db_id, sql)
        if success:
            print(f"  {metric}: {value}")
        else:
            print(f"  {metric}: {message}")

    print("\n" + "="*60)
    print("Fixing cards...\n")

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

        # Get current query to see what's wrong
        current_query = ""
        dataset_query = card.get("dataset_query", {})
        if dataset_query.get("type") == "native":
            current_query = dataset_query.get("native", {}).get("query", "")
        
        print(f"Card: {card_name} (id={card_id})")
        if current_query:
            print(f"  Current query (first 100 chars): {current_query[:100]}...")
        
        # Fix based on exact card name
        if "Orders" in card_name and "Executive" in card_name:
            sql = """
SELECT SUM(orders) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            if fix_card(headers, card_id, db_id, sql):
                print(f"  ✓ Fixed with correct Orders query")
                updated += 1
            else:
                print(f"  ✗ Failed to fix")

        elif "Revenue" in card_name and "Executive" in card_name:
            sql = """
SELECT SUM(revenue) AS total_revenue
FROM public_marts.fact_kpi_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            if fix_card(headers, card_id, db_id, sql):
                print(f"  ✓ Fixed with correct Revenue query")
                updated += 1
            else:
                print(f"  ✗ Failed to fix")

        elif "Spend" in card_name and "Executive" in card_name:
            sql = """
SELECT SUM(spend) AS total_spend
FROM public_marts.fact_spend_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            if fix_card(headers, card_id, db_id, sql):
                print(f"  ✓ Fixed with correct Spend query")
                updated += 1
            else:
                print(f"  ✗ Failed to fix")

        elif "Impressions" in card_name and "Executive" in card_name:
            sql = """
SELECT SUM(impressions) AS total_impressions
FROM public_marts.fact_spend_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            if fix_card(headers, card_id, db_id, sql):
                print(f"  ✓ Fixed with correct Impressions query")
                updated += 1
            else:
                print(f"  ✗ Failed to fix")

        elif "Clicks" in card_name and "Executive" in card_name:
            sql = """
SELECT SUM(clicks) AS total_clicks
FROM public_marts.fact_spend_daily
WHERE client_slug = 'expand'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            if fix_card(headers, card_id, db_id, sql):
                print(f"  ✓ Fixed with correct Clicks query")
                updated += 1
            else:
                print(f"  ✗ Failed to fix")

    print(f"\n✓ Fixed {updated} cards")
    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
