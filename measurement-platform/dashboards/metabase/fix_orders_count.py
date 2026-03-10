#!/usr/bin/env python3
"""
Fix the orders query to show total orders, not just 7.
The current query shows orders per day, but the card might be displaying incorrectly.
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
    print("Checking orders queries...\n")

    # First, let's check what the actual data shows
    db_id = get_database_id(headers)
    if db_id:
        print("Verifying data in fact_kpi_daily:")
        print("  Run in Supabase SQL Editor:")
        print("  SELECT SUM(orders) as total_orders")
        print("  FROM public_marts.fact_kpi_daily")
        print("  WHERE client_slug = 'expand'")
        print("    AND report_date >= '2025-03-01'")
        print("    AND report_date <= '2026-03-01';")
        print()

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
        current_sql = card.get("dataset_query", {}).get("native", {}).get("query", "")
        
        # Check if this is the orders card that's showing 7
        if "orders" in card_name.lower() or ("k.orders" in current_sql.lower() and "COALESCE(k.orders" in current_sql):
            print(f"Found orders card: {card_name} (id={card_id})")
            print(f"Current query returns orders per day (time series)")
            print(f"Card might be showing only one day's orders (7) instead of total")
            print()
            
            # Check if it's a time series or scalar
            display_type = card.get("display", "")
            if display_type in ["line", "bar", "area"]:
                print("  Card is a time series chart - this is correct for showing orders over time")
                print("  The issue might be:")
                print("    1. Only one day has data")
                print("    2. The date range is too narrow")
                print("    3. The visualization is showing the wrong metric")
            else:
                print("  Card should show total orders, not per-day")
                # If it's a scalar/number card, we should sum all orders
                if "scalar" in display_type or "table" in display_type:
                    # Extract client_slug and date range from existing query
                    has_client_slug = "client_slug" in current_sql.lower()
                    existing_tags = card.get("dataset_query", {}).get("native", {}).get("template-tags", {})
                    
                    if has_client_slug:
                        new_sql = """
SELECT SUM(orders) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE client_slug = {{client_slug}}
  AND report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
                        template_tags = existing_tags if existing_tags else {
                            "client_slug": {"name": "client_slug", "type": "text"},
                            "report_date_start": {"name": "report_date_start", "type": "date"},
                            "report_date_end": {"name": "report_date_end", "type": "date"},
                        }
                    else:
                        new_sql = """
SELECT SUM(orders) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
                        template_tags = {
                            "report_date_start": {"name": "report_date_start", "type": "date"},
                            "report_date_end": {"name": "report_date_end", "type": "date"},
                        }
                    
                    if update_card(headers, card_id, new_sql, template_tags):
                        print(f"  ✓ Updated to show total orders")
                        updated += 1

    print(f"\n✓ Checked orders cards")
    if updated > 0:
        print(f"  Updated {updated} card(s) to show total orders")
    else:
        print(f"  No changes needed, or card is correctly showing time series")
    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard['id']}")
    print("\nTo verify the data, run the SQL query shown above in Supabase.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
