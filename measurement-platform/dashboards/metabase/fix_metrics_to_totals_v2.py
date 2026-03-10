#!/usr/bin/env python3
"""
Fix executive and customer metric cards to show totals instead of averages/per-day.
This version preserves existing template tags and handles hardcoded client_slug values.
"""
from __future__ import annotations

import os
import sys
import re
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


def extract_client_slug(current_sql: str) -> tuple[str | None, bool]:
    """Extract client_slug value and whether it's a variable."""
    # Check if it's a variable
    if "{{client_slug}}" in current_sql or "'client_slug'" in current_sql.lower():
        return None, True
    
    # Try to extract hardcoded value
    patterns = [
        r"client_slug\s*=\s*['\"]([^'\"]+)['\"]",
        r"client_slug\s*=\s*([a-zA-Z_]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, current_sql, re.IGNORECASE)
        if match:
            return match.group(1), False
    
    return None, False


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
        print(f"  Failed: {r.status_code} {r.text[:300]}")
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
    print("Updating metrics to show totals...\n")

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
        existing_tags = card.get("dataset_query", {}).get("native", {}).get("template-tags", {})
        
        # Extract client_slug info
        client_value, is_variable = extract_client_slug(current_sql)
        has_client_slug = client_value is not None or is_variable
        
        # Build template tags - preserve existing ones
        template_tags = existing_tags.copy() if existing_tags else {}
        
        # Add date tags if missing
        if "report_date_start" not in template_tags:
            template_tags["report_date_start"] = {
                "id": str(uuid.uuid4()).replace("-", "")[:8],
                "name": "report_date_start",
                "display-name": "Start date",
                "type": "date",
            }
        if "report_date_end" not in template_tags:
            template_tags["report_date_end"] = {
                "id": str(uuid.uuid4()).replace("-", "")[:8],
                "name": "report_date_end",
                "display-name": "End date",
                "type": "date",
            }
        
        # Update Orders card
        if "Orders" in card_name and "Executive" in card_name:
            print(f"Updating: {card_name}")
            if is_variable:
                new_sql = """
SELECT SUM(orders) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE client_slug = {{client_slug}}
  AND report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            elif client_value:
                new_sql = f"""
SELECT SUM(orders) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE client_slug = '{client_value}'
  AND report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            else:
                new_sql = """
SELECT SUM(orders) AS total_orders
FROM public_marts.fact_kpi_daily
WHERE report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated")
                updated += 1

        # Update Revenue card
        elif "Revenue" in card_name and "Executive" in card_name:
            print(f"Updating: {card_name}")
            if is_variable:
                new_sql = """
SELECT SUM(revenue) AS total_revenue
FROM public_marts.fact_kpi_daily
WHERE client_slug = {{client_slug}}
  AND report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            elif client_value:
                new_sql = f"""
SELECT SUM(revenue) AS total_revenue
FROM public_marts.fact_kpi_daily
WHERE client_slug = '{client_value}'
  AND report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            else:
                new_sql = """
SELECT SUM(revenue) AS total_revenue
FROM public_marts.fact_kpi_daily
WHERE report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated")
                updated += 1

        # Update Spend card
        elif "Spend" in card_name and "Executive" in card_name:
            print(f"Updating: {card_name}")
            if is_variable:
                new_sql = """
SELECT SUM(spend) AS total_spend
FROM public_marts.fact_spend_daily
WHERE client_slug = {{client_slug}}
  AND report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            elif client_value:
                new_sql = f"""
SELECT SUM(spend) AS total_spend
FROM public_marts.fact_spend_daily
WHERE client_slug = '{client_value}'
  AND report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            else:
                new_sql = """
SELECT SUM(spend) AS total_spend
FROM public_marts.fact_spend_daily
WHERE report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated")
                updated += 1

        # Update Impressions card
        elif "Impressions" in card_name and "Executive" in card_name:
            print(f"Updating: {card_name}")
            if is_variable:
                new_sql = """
SELECT SUM(impressions) AS total_impressions
FROM public_marts.fact_spend_daily
WHERE client_slug = {{client_slug}}
  AND report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            elif client_value:
                new_sql = f"""
SELECT SUM(impressions) AS total_impressions
FROM public_marts.fact_spend_daily
WHERE client_slug = '{client_value}'
  AND report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            else:
                new_sql = """
SELECT SUM(impressions) AS total_impressions
FROM public_marts.fact_spend_daily
WHERE report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated")
                updated += 1

        # Update Clicks card
        elif "Clicks" in card_name and "Executive" in card_name:
            print(f"Updating: {card_name}")
            if is_variable:
                new_sql = """
SELECT SUM(clicks) AS total_clicks
FROM public_marts.fact_spend_daily
WHERE client_slug = {{client_slug}}
  AND report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            elif client_value:
                new_sql = f"""
SELECT SUM(clicks) AS total_clicks
FROM public_marts.fact_spend_daily
WHERE client_slug = '{client_value}'
  AND report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            else:
                new_sql = """
SELECT SUM(clicks) AS total_clicks
FROM public_marts.fact_spend_daily
WHERE report_date >= COALESCE({{report_date_start}}::date, '2020-01-01'::date)
  AND report_date <= COALESCE({{report_date_end}}::date, CURRENT_DATE)
"""
            if update_card(headers, card_id, new_sql, template_tags):
                print(f"  ✓ Updated")
                updated += 1

    print(f"\n✓ Updated {updated} metric cards to show totals")
    print(f"\n  -> {METABASE_URL}/dashboard/{dashboard['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
