#!/usr/bin/env python3
"""
Update customer metrics in a specific Metabase dashboard.
This script updates customer KPI cards to use the new fact_customers_daily and dim_customers tables.

Usage:
  python update_customer_metrics_v2.py "Dashboard Name"
  
Or set DASHBOARD_NAME environment variable:
  $env:DASHBOARD_NAME = "Client Performance Template v2"
  python update_customer_metrics_v2.py
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
    get_database_id,
    get_headers,
    list_dashboards,
    login,
    METABASE_URL,
)

# Date filter variables
_P1 = "{{report_date_start}}::date"
_P2 = "{{report_date_end}}::date"


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


def update_card(headers: dict, card_id: int, new_sql: str, template_tags: dict) -> bool:
    """Update a card's SQL query."""
    card = get_card(headers, card_id)
    if not card:
        print(f"  Card {card_id} not found")
        return False

    # Update the query
    dataset_query = card.get("dataset_query", {})
    native = dataset_query.get("native", {})
    native["query"] = new_sql
    native["template-tags"] = template_tags
    dataset_query["native"] = native
    card["dataset_query"] = dataset_query

    # Update the card
    r = requests.put(f"{METABASE_URL}/api/card/{card_id}", json=card, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        print(f"  Failed to update card {card_id}: {r.status_code} {r.text[:200]}")
        return False
    return True


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


def main() -> int:
    # Get dashboard name from command line or environment
    dashboard_name = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DASHBOARD_NAME", "")
    
    if not dashboard_name:
        print("Error: Please provide dashboard name as argument or set DASHBOARD_NAME env var", file=sys.stderr)
        print("Usage: python update_customer_metrics_v2.py 'Dashboard Name'", file=sys.stderr)
        return 1

    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    db_id = get_database_id(headers)
    if not db_id:
        print("No database found.", file=sys.stderr)
        return 1

    # Find the dashboard
    dashboard = get_dashboard(headers, dashboard_name)
    if not dashboard:
        print(f"Dashboard '{dashboard_name}' not found.", file=sys.stderr)
        print("\nAvailable dashboards:", file=sys.stderr)
        dashboards = list_dashboards(headers)
        for dash in dashboards:
            print(f"  - {dash.get('name')} (id={dash.get('id')})", file=sys.stderr)
        return 1

    print(f"Found dashboard: {dashboard_name} (id={dashboard['id']})")
    print("Updating customer metric cards...\n")

    template_tags = build_template_tags()
    updated = 0
    skipped = 0

    # Get all cards in the dashboard
    dashcards = dashboard.get("dashcards", [])
    for dashcard in dashcards:
        card_id = dashcard.get("card_id")
        if not card_id:
            continue

        card = get_card(headers, card_id)
        if not card:
            continue

        card_name = card.get("name", "")
        print(f"Checking: {card_name}")

        # Update New Customers
        if "New Customers" in card_name and "Returning" not in card_name:
            new_sql = f"""
SELECT COALESCE(SUM(new_customers), 0) AS new_customers
FROM public_marts.fact_customers_daily
WHERE report_date >= {_P1} AND report_date <= {_P2}
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated: {card_name}")
                updated += 1
            else:
                print(f"  ✗ Failed: {card_name}")

        # Update Returning Customers
        elif "Returning Customers" in card_name:
            new_sql = f"""
SELECT COALESCE(SUM(returning_customers), 0) AS returning_customers
FROM public_marts.fact_customers_daily
WHERE report_date >= {_P1} AND report_date <= {_P2}
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated: {card_name}")
                updated += 1
            else:
                print(f"  ✗ Failed: {card_name}")

        # Update Total Customers / Total Unique Customers / Customers (proxy)
        elif (("Total Customers" in card_name or "Total Unique Customers" in card_name or "Customers (proxy" in card_name) 
              and "New" not in card_name and "Returning" not in card_name):
            new_sql = f"""
SELECT COUNT(DISTINCT customer_identifier) AS total_customers
FROM public_marts.fact_customers_daily
WHERE report_date >= {_P1} AND report_date <= {_P2}
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated: {card_name}")
                updated += 1
            else:
                print(f"  ✗ Failed: {card_name}")

        # Update LTV (but not LTV:CAC)
        elif "LTV" in card_name and "LTV:CAC" not in card_name and "Ratio" not in card_name:
            new_sql = f"""
SELECT ROUND(AVG(lifetime_revenue)::numeric, 2) AS avg_ltv
FROM public_marts.dim_customers
WHERE first_order_date >= {_P1} AND first_order_date <= {_P2}
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated: {card_name}")
                updated += 1
            else:
                print(f"  ✗ Failed: {card_name}")
        else:
            skipped += 1

    print(f"\n✓ Updated {updated} customer metric cards")
    if skipped > 0:
        print(f"  (Skipped {skipped} cards that don't match customer metric patterns)")
    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard['id']}")
    print("\nNote: Make sure to:")
    print("  1. Link the date filters to the updated cards")
    print("  2. Verify the metrics show correct values (should be ~18,441 total customers, not 7)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
