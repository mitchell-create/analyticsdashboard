#!/usr/bin/env python3
"""
Verify what the executive metric queries are actually returning.
Tests each query and shows the actual values.
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


def test_query(headers: dict, db_id: int, sql: str) -> tuple[bool, any]:
    """Test a SQL query and return the result."""
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
        if rows:
            return True, rows[0][0] if rows[0] else None
        return True, None
    else:
        return False, f"Error {r.status_code}: {r.text[:200]}"


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

    print(f"Dashboard: {dashboard_name} (id={dashboard['id']})")
    print(f"Database id: {db_id}\n")
    print("="*80)
    print("TESTING CORRECT QUERIES:")
    print("="*80)

    # Test what the correct queries should return
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
        success, result = test_query(headers, db_id, sql)
        if success:
            print(f"{metric:15} = {result}")
        else:
            print(f"{metric:15} = ERROR: {result}")

    print("\n" + "="*80)
    print("CHECKING ACTUAL CARD QUERIES:")
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
        if "Executive" not in card_name:
            continue

        dataset_query = card.get("dataset_query", {})
        if dataset_query.get("type") == "native":
            sql = dataset_query.get("native", {}).get("query", "")
            print(f"\n{card_name} (id={card_id}):")
            print(f"  SQL: {sql[:150]}..." if len(sql) > 150 else f"  SQL: {sql}")
            
            # Test what this query returns
            success, result = test_query(headers, db_id, sql)
            if success:
                print(f"  Returns: {result}")
            else:
                print(f"  Error: {result}")

    print("\n" + "="*80)
    print("If all queries return 18,439, check:")
    print("  1. Does fact_kpi_daily have data for client_slug='expand'?")
    print("  2. Does fact_spend_daily have data for client_slug='expand'?")
    print("  3. Run in Supabase: SELECT COUNT(*) FROM public_marts.fact_kpi_daily WHERE client_slug='expand';")
    return 0


if __name__ == "__main__":
    sys.exit(main())
