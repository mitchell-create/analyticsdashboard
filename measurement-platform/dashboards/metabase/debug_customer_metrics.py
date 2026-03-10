#!/usr/bin/env python3
"""
Debug customer metrics - check what queries are actually being used
and verify the data in the tables.
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

    print(f"Dashboard: {dashboard_name} (id={dashboard['id']})\n")
    print("="*80)
    print("CUSTOMER-RELATED CARDS:")
    print("="*80)

    dashcards = dashboard.get("dashcards", [])
    for dashcard in dashcards:
        card_id = dashcard.get("card_id")
        if not card_id:
            continue

        card = get_card(headers, card_id)
        if not card:
            continue

        card_name = card.get("name", "")
        
        # Check if it's customer-related
        if any(keyword in card_name.lower() for keyword in ["customer", "ltv", "new customer", "returning"]):
            print(f"\nCard: {card_name} (id={card_id})")
            dataset_query = card.get("dataset_query", {})
            if dataset_query.get("type") == "native":
                sql = dataset_query.get("native", {}).get("query", "")
                print(f"SQL Query:")
                print(sql[:500] + "..." if len(sql) > 500 else sql)
                print("-" * 80)

    print("\n" + "="*80)
    print("VERIFYING DATA IN TABLES:")
    print("="*80)
    
    db_id = get_database_id(headers)
    if db_id:
        # Check fact_customers_daily
        print("\n1. Checking fact_customers_daily:")
        print("   Run in Supabase SQL Editor:")
        print("   SELECT COUNT(*) as total_days, SUM(new_customers) as total_new, SUM(returning_customers) as total_returning")
        print("   FROM public_marts.fact_customers_daily;")
        
        print("\n2. Checking dim_customers:")
        print("   SELECT COUNT(*) as total_customers FROM public_marts.dim_customers;")
        
        print("\n3. Sample data from fact_customers_daily (last 10 days):")
        print("   SELECT * FROM public_marts.fact_customers_daily ORDER BY report_date DESC LIMIT 10;")

    return 0


if __name__ == "__main__":
    sys.exit(main())
