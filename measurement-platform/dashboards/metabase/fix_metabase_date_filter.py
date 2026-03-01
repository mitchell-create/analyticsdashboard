#!/usr/bin/env python3
"""
Apply Option A: set each Executive Overview and Channel Performance question
to use variable-free SQL so the dashboard Date filter can link to the date column.

Run after Metabase is connected. Same env as create_mvp_dashboards.py:
  METABASE_URL, METABASE_EMAIL, METABASE_PASSWORD (or METABASE_API_KEY)
"""
from __future__ import annotations

import os
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

# Reuse auth and question definitions from create_mvp_dashboards
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from create_mvp_dashboards import (
    CHANNEL_PERFORMANCE_QUESTIONS,
    EXEC_OVERVIEW_QUESTIONS,
    get_headers,
    login,
    METABASE_URL,
)


def list_cards(headers: dict) -> list[dict]:
    r = requests.get(f"{METABASE_URL}/api/card", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"GET /api/card failed: {r.status_code}", file=sys.stderr)
        return []
    data = r.json()
    if isinstance(data, list):
        return data
    return data.get("data", [])


def get_card(headers: dict, card_id: int) -> dict | None:
    r = requests.get(f"{METABASE_URL}/api/card/{card_id}", headers=headers, timeout=30)
    if r.status_code != 200:
        return None
    return r.json()


def update_card_option_b(
    headers: dict,
    card_id: int,
    sql: str,
    template_tags: dict,
    display: str | None = None,
    viz: dict | None = None,
) -> bool:
    """Update a card with Option B: SQL containing {{report_date}} and dimension template-tags."""
    card = get_card(headers, card_id)
    if not card:
        print(f"  Could not fetch card {card_id}", file=sys.stderr)
        return False
    db_id = card.get("database_id")
    if not db_id:
        print(f"  Card {card_id} has no database_id", file=sys.stderr)
        return False
    dq = {
        "type": "native",
        "database": db_id,
        "native": {
            "query": sql,
            "template-tags": template_tags,
        },
    }
    card["dataset_query"] = dq
    if display is not None:
        card["display"] = display
    if viz is not None:
        card["visualization_settings"] = {**(card.get("visualization_settings") or {}), **viz}
    r = requests.put(
        f"{METABASE_URL}/api/card/{card_id}",
        json=card,
        headers=headers,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        print(f"  PUT card {card_id} failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return False
    return True


def update_card_native_query(
    headers: dict, card_id: int, sql: str, display: str | None = None, viz: dict | None = None
) -> bool:
    card = get_card(headers, card_id)
    if not card:
        print(f"  Could not fetch card {card_id}", file=sys.stderr)
        return False
    # Build a full dataset_query so Metabase never sees empty or missing :database (fixes "query cannot be empty" / "Query must include :database")
    db_id = card.get("database_id")
    if not db_id:
        print(f"  Card {card_id} has no database_id", file=sys.stderr)
        return False
    dq = {
        "type": "native",
        "database": db_id,
        "native": {
            "query": sql,
            "template-tags": {},
        },
    }
    card["dataset_query"] = dq
    if display is not None:
        card["display"] = display
    if viz is not None:
        card["visualization_settings"] = {**(card.get("visualization_settings") or {}), **viz}
    r = requests.put(
        f"{METABASE_URL}/api/card/{card_id}",
        json=card,
        headers=headers,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        print(f"  PUT card {card_id} failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return False
    return True


def main() -> int:
    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    # name -> canonical SQL (and optional display/viz)
    canonical: dict[str, dict] = {}
    for q in EXEC_OVERVIEW_QUESTIONS + CHANNEL_PERFORMANCE_QUESTIONS:
        canonical[q["name"]] = {
            "sql": q["sql"],
            "display": q.get("display"),
            "viz": q.get("viz"),
        }

    cards = list_cards(headers)
    if not cards:
        print("No cards found.", file=sys.stderr)
        return 1

    updated = 0
    for card in cards:
        name = card.get("name")
        if name not in canonical:
            continue
        c = canonical[name]
        if update_card_native_query(
            headers,
            card["id"],
            c["sql"],
            display=c.get("display"),
            viz=c.get("viz"),
        ):
            print(f"Updated: {name} (id={card['id']})")
            updated += 1
        else:
            print(f"Failed: {name} (id={card['id']})", file=sys.stderr)

    print(f"\nDone. Updated {updated} card(s). Add a dashboard Date filter and link it to these cards.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
