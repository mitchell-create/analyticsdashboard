#!/usr/bin/env python3
"""
Update Channel Performance cards to use 4 date filters and show period-over-period % change.

Filters:
  - Start date, End date (primary period)
  - Comparison start date, Comparison end date (comparison period)

Each card shows metrics for both periods plus % change.

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
from fix_metabase_date_filter import get_card, list_cards, update_card_option_b

# Optional date ranges for primary and comparison windows.
# Use optional AND blocks so applying one variable never comments out the rest
# of the predicate chain.
_PRIMARY_RANGE = """1=1
[[AND report_date >= {{report_date_start}}::date]]
[[AND report_date <= {{report_date_end}}::date]]"""
_COMPARISON_RANGE = """1=1
[[AND report_date >= {{comparison_date_start}}::date]]
[[AND report_date <= {{comparison_date_end}}::date]]"""

CHANNEL_COMPARISON_QUESTIONS = [
    {
        "name": "Spend by channel over time",
        "sql": f"""
WITH p1 AS (
  SELECT channel, COALESCE(SUM(spend), 0) AS spend
  FROM public_marts.fact_spend_daily
  WHERE {_PRIMARY_RANGE}
  GROUP BY channel
),
p2 AS (
  SELECT channel, COALESCE(SUM(spend), 0) AS spend
  FROM public_marts.fact_spend_daily
  WHERE {_COMPARISON_RANGE}
  GROUP BY channel
)
SELECT
  COALESCE(p1.channel, p2.channel) AS channel,
  COALESCE(p1.spend, 0) AS period_spend,
  COALESCE(p2.spend, 0) AS comparison_spend,
  CASE WHEN COALESCE(p2.spend, 0) = 0 THEN 0
       ELSE ROUND(((COALESCE(p1.spend, 0) - COALESCE(p2.spend, 0)) / p2.spend * 100)::numeric, 1) END AS pct_change
FROM p1
FULL OUTER JOIN p2 ON p1.channel = p2.channel
ORDER BY period_spend DESC NULLS LAST
""",
        "display": "table",
        "viz": {},
    },
    {
        "name": "ROAS by channel",
        "sql": f"""
WITH rev_p1 AS (
  SELECT COALESCE(SUM(revenue), 0) AS revenue FROM public_marts.fact_kpi_daily
  WHERE {_PRIMARY_RANGE}
),
rev_p2 AS (
  SELECT COALESCE(SUM(revenue), 0) AS revenue FROM public_marts.fact_kpi_daily
  WHERE {_COMPARISON_RANGE}
),
spend_p1 AS (
  SELECT channel, COALESCE(SUM(spend), 0) AS spend
  FROM public_marts.fact_spend_daily
  WHERE {_PRIMARY_RANGE}
  GROUP BY channel
),
spend_p2 AS (
  SELECT channel, COALESCE(SUM(spend), 0) AS spend
  FROM public_marts.fact_spend_daily
  WHERE {_COMPARISON_RANGE}
  GROUP BY channel
)
SELECT
  COALESCE(s1.channel, s2.channel) AS channel,
  CASE WHEN COALESCE(s1.spend, 0) = 0 THEN 0 ELSE (SELECT revenue FROM rev_p1) / NULLIF(s1.spend, 0) END AS period_roas,
  CASE WHEN COALESCE(s2.spend, 0) = 0 THEN 0 ELSE (SELECT revenue FROM rev_p2) / NULLIF(s2.spend, 0) END AS comparison_roas,
  CASE WHEN COALESCE(s2.spend, 0) = 0 OR (SELECT revenue FROM rev_p2) = 0 THEN 0
       ELSE ROUND((((SELECT revenue FROM rev_p1) / NULLIF(COALESCE(s1.spend, 0), 0) - (SELECT revenue FROM rev_p2) / NULLIF(COALESCE(s2.spend, 0), 0))
         / NULLIF((SELECT revenue FROM rev_p2) / NULLIF(COALESCE(s2.spend, 0), 0), 0) * 100)::numeric, 1) END AS pct_change
FROM spend_p1 s1
FULL OUTER JOIN spend_p2 s2 ON s1.channel = s2.channel
ORDER BY period_roas DESC NULLS LAST
""",
        "display": "table",
        "viz": {},
    },
    {
        "name": "Impressions and clicks by channel",
        "sql": f"""
WITH p1 AS (
  SELECT channel,
    COALESCE(SUM(impressions), 0) AS impressions,
    COALESCE(SUM(clicks), 0) AS clicks
  FROM public_marts.fact_spend_daily
  WHERE {_PRIMARY_RANGE}
  GROUP BY channel
),
p2 AS (
  SELECT channel,
    COALESCE(SUM(impressions), 0) AS impressions,
    COALESCE(SUM(clicks), 0) AS clicks
  FROM public_marts.fact_spend_daily
  WHERE {_COMPARISON_RANGE}
  GROUP BY channel
)
SELECT
  COALESCE(p1.channel, p2.channel) AS channel,
  COALESCE(p1.impressions, 0) AS period_impressions,
  COALESCE(p2.impressions, 0) AS comparison_impressions,
  CASE WHEN COALESCE(p2.impressions, 0) = 0 THEN 0
       ELSE ROUND(((COALESCE(p1.impressions, 0) - COALESCE(p2.impressions, 0)) / p2.impressions * 100)::numeric, 1) END AS impressions_pct_change,
  COALESCE(p1.clicks, 0) AS period_clicks,
  COALESCE(p2.clicks, 0) AS comparison_clicks,
  CASE WHEN COALESCE(p2.clicks, 0) = 0 THEN 0
       ELSE ROUND(((COALESCE(p1.clicks, 0) - COALESCE(p2.clicks, 0)) / p2.clicks * 100)::numeric, 1) END AS clicks_pct_change
FROM p1
FULL OUTER JOIN p2 ON p1.channel = p2.channel
ORDER BY period_impressions DESC NULLS LAST
""",
        "display": "table",
        "viz": {},
    },
    {
        "name": "Spend share by channel",
        "sql": f"""
WITH p1 AS (
  SELECT channel, COALESCE(SUM(spend), 0) AS spend
  FROM public_marts.fact_spend_daily
  WHERE {_PRIMARY_RANGE}
  GROUP BY channel
),
p2 AS (
  SELECT channel, COALESCE(SUM(spend), 0) AS spend
  FROM public_marts.fact_spend_daily
  WHERE {_COMPARISON_RANGE}
  GROUP BY channel
)
SELECT
  COALESCE(p1.channel, p2.channel) AS channel,
  COALESCE(p1.spend, 0) AS period_spend,
  COALESCE(p2.spend, 0) AS comparison_spend,
  CASE WHEN COALESCE(p2.spend, 0) = 0 THEN 0
       ELSE ROUND(((COALESCE(p1.spend, 0) - COALESCE(p2.spend, 0)) / p2.spend * 100)::numeric, 1) END AS pct_change
FROM p1
FULL OUTER JOIN p2 ON p1.channel = p2.channel
ORDER BY period_spend DESC NULLS LAST
""",
        "display": "table",
        "viz": {},
    },
]


def build_template_tags() -> dict:
    """Four date variables: primary period + comparison period."""
    return {
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
        "comparison_date_start": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "comparison_date_start",
            "display-name": "Comparison start date",
            "type": "date",
        },
        "comparison_date_end": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "comparison_date_end",
            "display-name": "Comparison end date",
            "type": "date",
        },
    }


def main() -> int:
    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    cards = list_cards(headers)
    if not cards:
        print("No cards found.", file=sys.stderr)
        return 1

    template_tags = build_template_tags()
    by_name = {q["name"]: q for q in CHANNEL_COMPARISON_QUESTIONS}
    updated = 0
    for card in cards:
        name = card.get("name")
        if name not in by_name:
            continue
        q = by_name[name]
        if update_card_option_b(
            headers,
            card["id"],
            q["sql"],
            template_tags,
            display=q.get("display"),
            viz=q.get("viz"),
        ):
            print(f"Updated: {name} (id={card['id']})")
            updated += 1
        else:
            print(f"Failed: {name} (id={card['id']})", file=sys.stderr)

    print(
        f"\nDone. Updated {updated} card(s).\n"
        "Next: Add 4 dashboard filters (Date type, Single date):\n"
        "  - Start date, End date (primary period)\n"
        "  - Comparison start date, Comparison end date (comparison period)\n"
        "Link each filter to all 4 Channel Performance cards. See CHANNEL_PERIOD_COMPARISON_SETUP.md"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
