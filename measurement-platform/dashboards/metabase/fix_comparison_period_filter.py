#!/usr/bin/env python3
"""
Fix "A number variable can only be connected to a number filter with Equal to operator" error.

This is a known Metabase bug (GitHub #44266) in versions before v0.50.7. Workaround:
change period_days from type "number" to type "text" so it works with a Text filter.

Run with same env as create_mvp_dashboards.py:
  METABASE_URL, METABASE_EMAIL, METABASE_PASSWORD (or METABASE_API_KEY)
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
from create_mvp_dashboards import get_headers, login, METABASE_URL
from create_comparison_dashboard import COMPARISON_SQL

CARD_NAME = "Key metrics: Current vs Prior period"


def list_cards(headers: dict) -> list[dict]:
    r = requests.get(f"{METABASE_URL}/api/card", headers=headers, timeout=30)
    if r.status_code != 200:
        return []
    data = r.json()
    return data.get("data", data) if isinstance(data, dict) else (data if isinstance(data, list) else [])


def get_card(headers: dict, card_id: int) -> dict | None:
    r = requests.get(f"{METABASE_URL}/api/card/{card_id}", headers=headers, timeout=30)
    return r.json() if r.status_code == 200 else None


def main() -> int:
    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    cards = list_cards(headers)
    target = next((c for c in cards if c.get("name") == CARD_NAME), None)
    if not target:
        print(f"Card '{CARD_NAME}' not found. Run create_comparison_dashboard.py first.", file=sys.stderr)
        return 1

    template_tags = {
        "period_days": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "period_days",
            "display-name": "Period (days)",
            "type": "number",
            "default": 7,
        },
    }

    card = get_card(headers, target["id"])
    if not card:
        print(f"Could not fetch card {target['id']}", file=sys.stderr)
        return 1

    card["dataset_query"] = {
        "type": "native",
        "database": card["database_id"],
        "native": {
            "query": COMPARISON_SQL,
            "template-tags": template_tags,
        },
    }

    r = requests.put(
        f"{METABASE_URL}/api/card/{target['id']}",
        json=card,
        headers=headers,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        print(f"Update failed: {r.status_code} {r.text[:300]}", file=sys.stderr)
        return 1

    print(f"Updated '{CARD_NAME}' to use Number variable (period_days).")
    print("\nNext steps:")
    print("1. Remove the existing Period filter from the dashboard (if any).")
    print("2. Add a new filter: Number type, label 'Period (days)', default 7.")
    print("3. Link it to the card's period_days variable.")
    print("4. Use values 7, 14, or 30 for different period lengths.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
