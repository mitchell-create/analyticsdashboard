#!/usr/bin/env python3
"""
Fix customer metric cards to work even without date filters linked.
Uses default date ranges if filters aren't linked.
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
    """Date variables with defaults."""
    return {
        "report_date_start": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "report_date_start",
            "display-name": "Start date",
            "type": "date",
            "default": None,  # Will use COALESCE in SQL
        },
        "report_date_end": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "report_date_end",
            "display-name": "End date",
            "type": "date",
            "default": None,  # Will use COALESCE in SQL
        },
    }


def main() -> int:
    dashboard_name = sys.argv[1] if len(sys.argv) > 1 else "Client Performance Template v2"
    
    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    dashboard = get_dashboard(headers, dashboard_name)
    if not dashboard:
        print(f"Dashboard '{dashboard_name}' not found.", file=sys.stderr)
        return 1

    print(f"Found dashboard: {dashboard_name} (id={dashboard['id']})")
    print("Updating customer metric cards with default date handling...\n")

    template_tags = build_template_tags()
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
        print(f"Checking: {card_name}")

        # Update New Customers - with default to all time if no date filter
        if "New Customers" in card_name and "Returning" not in card_name:
            new_sql = """
SELECT COALESCE(SUM(new_customers), 0) AS new_customers
FROM public_marts.fact_customers_daily
WHERE report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated: {card_name}")
                updated += 1

        # Update Returning Customers
        elif "Returning Customers" in card_name:
            new_sql = """
SELECT COALESCE(SUM(returning_customers), 0) AS returning_customers
FROM public_marts.fact_customers_daily
WHERE report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated: {card_name}")
                updated += 1

        # Update Total Customers - use dim_customers with default to all time
        elif (("Total Customers" in card_name or "Customers (proxy" in card_name) 
              and "New" not in card_name and "Returning" not in card_name):
            new_sql = """
SELECT COUNT(*) AS total_customers
FROM public_marts.dim_customers
WHERE first_order_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND first_order_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated: {card_name}")
                updated += 1

        # Update LTV
        elif "LTV" in card_name and "LTV:CAC" not in card_name and "Ratio" not in card_name:
            new_sql = """
SELECT ROUND(AVG(lifetime_revenue)::numeric, 2) AS avg_ltv
FROM public_marts.dim_customers
WHERE first_order_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND first_order_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated: {card_name}")
                updated += 1

    print(f"\n✓ Updated {updated} customer metric cards")
    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard['id']}")
    print("\nThe queries now use default date ranges (2020-01-01 to today) if filters aren't linked.")
    print("This should show all customers (~18,441) when no date filter is set.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
