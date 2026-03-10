#!/usr/bin/env python3
"""
Fix the "Customers (proxy: orders)" card to actually show customers, not orders.
This card is currently showing orders count instead of customer count.
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
    print("Fixing 'Customers (proxy: orders)' card to show actual customers...\n")

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
        
        # Find the "Customers (proxy: orders)" card
        if "Customers (proxy" in card_name:
            print(f"Found card: {card_name} (id={card_id})")
            
            # Get the current query to check for client_slug
            current_sql = card.get("dataset_query", {}).get("native", {}).get("query", "")
            has_client_slug = "client_slug" in current_sql.lower()
            
            # Build template tags from existing card or create new ones
            existing_tags = card.get("dataset_query", {}).get("native", {}).get("template-tags", {})
            
            if has_client_slug:
                # The card filters by client_slug, so we need to count customers for that specific store
                # We'll need to join with the unified orders to get store_name
                new_sql = """
WITH customer_store AS (
  SELECT DISTINCT
    customer_identifier,
    store_name,
    MIN(report_date) as first_order_date
  FROM public_marts.stg_shopify_orders_unified
  WHERE report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
    AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
  GROUP BY customer_identifier, store_name
)
SELECT COUNT(DISTINCT customer_identifier) AS total_customers
FROM customer_store
WHERE store_name = {{client_slug}}
"""
                # Add client_slug to template tags if it exists
                if "client_slug" in existing_tags:
                    template_tags = existing_tags
                else:
                    template_tags = {
                        "client_slug": {
                            "id": str(uuid.uuid4()).replace("-", "")[:8],
                            "name": "client_slug",
                            "display-name": "Client",
                            "type": "text",
                        },
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
            else:
                # No client_slug filter, just count all customers
                new_sql = """
SELECT COUNT(*) AS total_customers
FROM public_marts.dim_customers
WHERE first_order_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND first_order_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
                template_tags = {
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
            
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated: {card_name}")
                print(f"    Query now counts actual customers instead of orders")
                updated += 1
            else:
                print(f"  ✗ Failed to update: {card_name}")

    print(f"\n✓ Updated {updated} card(s)")
    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
