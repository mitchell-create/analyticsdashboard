#!/usr/bin/env python3
"""
Check for errors in dashboard cards and show what's wrong.
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


def test_query(headers: dict, db_id: int, sql: str) -> tuple[bool, str]:
    """Test a SQL query by running it."""
    payload = {
        "database_id": db_id,
        "query": {
            "type": "native",
            "native": {"query": sql},
        },
    }
    r = requests.post(f"{METABASE_URL}/api/dataset", json=payload, headers=headers, timeout=30)
    if r.status_code == 200:
        return True, "Query successful"
    else:
        return False, f"Error {r.status_code}: {r.text[:500]}"


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

    print(f"Checking cards in: {dashboard_name} (id={dashboard['id']})\n")
    print("="*80)

    dashcards = dashboard.get("dashcards", [])
    error_count = 0
    
    for dashcard in dashcards:
        card_id = dashcard.get("card_id")
        if not card_id:
            continue

        card = get_card(headers, card_id)
        if not card:
            continue

        card_name = card.get("name", "")
        
        # Check executive metrics
        if "Executive" in card_name and any(metric in card_name for metric in ["Orders", "Revenue", "Spend", "Impressions", "Clicks"]):
            print(f"\nCard: {card_name} (id={card_id})")
            
            dataset_query = card.get("dataset_query", {})
            if dataset_query.get("type") == "native":
                sql = dataset_query.get("native", {}).get("query", "")
                template_tags = dataset_query.get("native", {}).get("template-tags", {})
                
                print(f"  SQL (first 200 chars): {sql[:200]}...")
                print(f"  Template tags: {list(template_tags.keys())}")
                
                # Test the query
                success, message = test_query(headers, db_id, sql)
                if success:
                    print(f"  ✓ Query is valid")
                else:
                    print(f"  ✗ Query error: {message}")
                    error_count += 1
            else:
                print(f"  (Not a native SQL query)")

    print(f"\n" + "="*80)
    if error_count == 0:
        print("✓ No query errors found")
        print("\nIf cards are still showing errors in Metabase UI, the issue might be:")
        print("  1. Display type mismatch (card expects time series but query returns scalar)")
        print("  2. Missing date filter links")
        print("  3. Cache issues - try refreshing the dashboard")
    else:
        print(f"✗ Found {error_count} query error(s)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
