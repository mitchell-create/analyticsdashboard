#!/usr/bin/env python3
"""
Simple fix: Update executive metric cards to show totals.
Preserves all existing template tags and structure.
"""
from __future__ import annotations

import os
import sys
import re

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


def update_card_sql_only(headers: dict, card_id: int, new_sql: str) -> bool:
    """Update only the SQL query, preserving everything else."""
    card = get_card(headers, card_id)
    if not card:
        print(f"  Card {card_id} not found")
        return False

    # Only update the SQL query, keep everything else the same
    dataset_query = card.get("dataset_query", {})
    native = dataset_query.get("native", {})
    native["query"] = new_sql
    # Keep existing template-tags as-is
    dataset_query["native"] = native
    card["dataset_query"] = dataset_query

    # Update the card
    r = requests.put(f"{METABASE_URL}/api/card/{card_id}", json=card, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        print(f"  Failed: {r.status_code} {r.text[:300]}")
        return False
    return True


def extract_date_range(current_sql: str) -> tuple[str, str]:
    """Extract date range from SQL, return (start_date, end_date) or defaults."""
    # Look for date literals
    start_match = re.search(r"report_date\s*>=\s*date\s*['\"]([^'\"]+)['\"]", current_sql, re.IGNORECASE)
    end_match = re.search(r"report_date\s*<=\s*date\s*['\"]([^'\"]+)['\"]", current_sql, re.IGNORECASE)
    
    start_date = start_match.group(1) if start_match else "2020-01-01"
    end_date = end_match.group(1) if end_match else "CURRENT_DATE"
    
    return start_date, end_date


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
    print("Updating metrics to show totals (preserving existing structure)...\n")

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
        
        # Update Orders card - convert to total
        if "Orders" in card_name and "Executive" in card_name:
            print(f"Updating: {card_name}")
            # Extract client_slug and date range from current query
            has_client_slug = "client_slug" in current_sql.lower()
            client_match = re.search(r"client_slug\s*=\s*['\"]([^'\"]+)['\"]", current_sql, re.IGNORECASE)
            client_value = client_match.group(1) if client_match else None
            
            if client_value:
                new_sql = f"""
SELECT SUM(orders) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE client_slug = '{client_value}'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            else:
                new_sql = """
SELECT SUM(orders) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            if update_card_sql_only(headers, card_id, new_sql):
                print(f"  ✓ Updated")
                updated += 1

        # Update Revenue card
        elif "Revenue" in card_name and "Executive" in card_name:
            print(f"Updating: {card_name}")
            client_match = re.search(r"client_slug\s*=\s*['\"]([^'\"]+)['\"]", current_sql, re.IGNORECASE)
            client_value = client_match.group(1) if client_match else None
            
            if client_value:
                new_sql = f"""
SELECT SUM(revenue) AS total_revenue
FROM public_marts.fact_kpi_daily
WHERE client_slug = '{client_value}'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            else:
                new_sql = """
SELECT SUM(revenue) AS total_revenue
FROM public_marts.fact_kpi_daily
WHERE report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            if update_card_sql_only(headers, card_id, new_sql):
                print(f"  ✓ Updated")
                updated += 1

        # Update Spend card
        elif "Spend" in card_name and "Executive" in card_name:
            print(f"Updating: {card_name}")
            client_match = re.search(r"client_slug\s*=\s*['\"]([^'\"]+)['\"]", current_sql, re.IGNORECASE)
            client_value = client_match.group(1) if client_match else None
            
            if client_value:
                new_sql = f"""
SELECT SUM(spend) AS total_spend
FROM public_marts.fact_spend_daily
WHERE client_slug = '{client_value}'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            else:
                new_sql = """
SELECT SUM(spend) AS total_spend
FROM public_marts.fact_spend_daily
WHERE report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            if update_card_sql_only(headers, card_id, new_sql):
                print(f"  ✓ Updated")
                updated += 1

        # Update Impressions card
        elif "Impressions" in card_name and "Executive" in card_name:
            print(f"Updating: {card_name}")
            client_match = re.search(r"client_slug\s*=\s*['\"]([^'\"]+)['\"]", current_sql, re.IGNORECASE)
            client_value = client_match.group(1) if client_match else None
            
            if client_value:
                new_sql = f"""
SELECT SUM(impressions) AS total_impressions
FROM public_marts.fact_spend_daily
WHERE client_slug = '{client_value}'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            else:
                new_sql = """
SELECT SUM(impressions) AS total_impressions
FROM public_marts.fact_spend_daily
WHERE report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            if update_card_sql_only(headers, card_id, new_sql):
                print(f"  ✓ Updated")
                updated += 1

        # Update Clicks card
        elif "Clicks" in card_name and "Executive" in card_name:
            print(f"Updating: {card_name}")
            client_match = re.search(r"client_slug\s*=\s*['\"]([^'\"]+)['\"]", current_sql, re.IGNORECASE)
            client_value = client_match.group(1) if client_match else None
            
            if client_value:
                new_sql = f"""
SELECT SUM(clicks) AS total_clicks
FROM public_marts.fact_spend_daily
WHERE client_slug = '{client_value}'
  AND report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            else:
                new_sql = """
SELECT SUM(clicks) AS total_clicks
FROM public_marts.fact_spend_daily
WHERE report_date >= date '2020-01-01'
  AND report_date <= CURRENT_DATE
"""
            if update_card_sql_only(headers, card_id, new_sql):
                print(f"  ✓ Updated")
                updated += 1

    print(f"\n✓ Updated {updated} metric cards")
    print(f"\nNote: These queries use hardcoded date ranges. To add date filters,")
    print("      you'll need to link dashboard filters in Metabase UI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
