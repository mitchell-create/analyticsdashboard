#!/usr/bin/env python3
"""
Apply date range filter: two date variables (report_date_start, report_date_end)
so the dashboard can use a proper "From X to Y" date range (or "Last 30 days").

Run after Metabase is connected. Same env as create_mvp_dashboards.py:
  METABASE_URL, METABASE_EMAIL, METABASE_PASSWORD (or METABASE_API_KEY)

Then add a dashboard "Date range" filter and link it to both variables.
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

# Date range: report_date_start and report_date_end (dashboard Date filters).
# Use optional AND blocks instead of the inline "-- default" trick; inline comments
# can swallow the rest of the WHERE clause when a variable is provided.
_DATE_RANGE_CLAUSE = """WHERE 1=1
[[AND report_date >= {{report_date_start}}::date]]
[[AND report_date <= {{report_date_end}}::date]]"""
_AND_DATE_RANGE = """
[[AND report_date >= {{report_date_start}}::date]]
[[AND report_date <= {{report_date_end}}::date]]"""
_AND_S_DATE_RANGE = """
[[AND s.report_date >= {{report_date_start}}::date]]
[[AND s.report_date <= {{report_date_end}}::date]]"""

DATE_RANGE_QUESTIONS = [
    {
        "name": "Daily revenue",
        "sql": "SELECT report_date AS date, COALESCE(SUM(revenue), 0) AS revenue FROM public_marts.fact_kpi_daily "
        + _DATE_RANGE_CLAUSE
        + " GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["revenue"]},
    },
    {
        "name": "Daily orders",
        "sql": "SELECT report_date AS date, COALESCE(SUM(orders), 0) AS orders FROM public_marts.fact_kpi_daily "
        + _DATE_RANGE_CLAUSE
        + " GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["orders"]},
    },
    {
        "name": "Spend by date",
        "sql": "SELECT report_date AS date, COALESCE(SUM(spend), 0) AS spend FROM public_marts.fact_spend_daily "
        + _DATE_RANGE_CLAUSE
        + " GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["spend"]},
    },
    {
        "name": "Total spend by channel",
        "sql": "SELECT channel, COALESCE(SUM(spend), 0) AS spend FROM public_marts.fact_spend_daily "
        + _DATE_RANGE_CLAUSE
        + " GROUP BY channel ORDER BY spend DESC",
        "display": "bar",
        "viz": {"graph.dimensions": ["channel"], "graph.metrics": ["spend"]},
    },
    {
        "name": "ROAS (revenue / spend)",
        "sql": """SELECT
  (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily WHERE 1=1 """
        + _AND_DATE_RANGE
        + """) AS revenue,
  (SELECT COALESCE(SUM(spend), 0) FROM public_marts.fact_spend_daily WHERE 1=1 """
        + _AND_DATE_RANGE
        + """) AS spend,
  CASE WHEN (SELECT COALESCE(SUM(spend), 0) FROM public_marts.fact_spend_daily WHERE 1=1 """
        + _AND_DATE_RANGE
        + """) = 0 THEN 0
       ELSE (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily WHERE 1=1 """
        + _AND_DATE_RANGE
        + """) / NULLIF((SELECT SUM(spend) FROM public_marts.fact_spend_daily WHERE 1=1 """
        + _AND_DATE_RANGE
        + """), 0) END AS roas""",
        "display": "table",
        "viz": {},
    },
    {
        "name": "Spend by channel over time",
        "sql": "SELECT report_date AS date, channel, COALESCE(SUM(spend), 0) AS spend FROM public_marts.fact_spend_daily "
        + _DATE_RANGE_CLAUSE
        + " GROUP BY report_date, channel ORDER BY report_date, channel",
        "display": "line",
        "viz": {"graph.dimensions": ["date", "channel"], "graph.metrics": ["spend"]},
    },
    {
        "name": "ROAS by channel",
        "sql": """SELECT s.channel,
  COALESCE(SUM(s.spend), 0) AS spend,
  (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily WHERE 1=1 """
        + _AND_DATE_RANGE
        + """) AS revenue,
  CASE WHEN SUM(s.spend) = 0 THEN 0 ELSE (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily WHERE 1=1 """
        + _AND_DATE_RANGE
        + """) / NULLIF(SUM(s.spend), 0) END AS roas
FROM public_marts.fact_spend_daily s
WHERE 1=1 """
        + _AND_S_DATE_RANGE
        + """
GROUP BY s.channel
ORDER BY spend DESC""",
        "display": "table",
        "viz": {},
    },
    {
        "name": "Impressions and clicks by channel",
        "sql": "SELECT report_date AS date, channel, SUM(impressions) AS impressions, SUM(clicks) AS clicks FROM public_marts.fact_spend_daily "
        + _DATE_RANGE_CLAUSE
        + " GROUP BY report_date, channel ORDER BY report_date, channel",
        "display": "line",
        "viz": {"graph.dimensions": ["date", "channel"], "graph.metrics": ["impressions", "clicks"]},
    },
    {
        "name": "Spend share by channel",
        "sql": "SELECT channel, COALESCE(SUM(spend), 0) AS spend FROM public_marts.fact_spend_daily "
        + _DATE_RANGE_CLAUSE
        + " GROUP BY channel ORDER BY spend DESC",
        "display": "pie",
        "viz": {"pie.dimension": "channel", "pie.metric": "spend"},
    },
    # Email & Klaviyo dashboard
    {
        "name": "Email sends by day",
        "sql": "SELECT report_date AS date, COALESCE(SUM(sent), 0) AS sent FROM public_marts.fact_klaviyo_daily "
        + _DATE_RANGE_CLAUSE
        + " GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["sent"]},
    },
    {
        "name": "Email opens and clicks by day",
        "sql": "SELECT report_date AS date, COALESCE(SUM(opens), 0) AS opens, COALESCE(SUM(clicks), 0) AS clicks FROM public_marts.fact_klaviyo_daily "
        + _DATE_RANGE_CLAUSE
        + " GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["opens", "clicks"]},
    },
    {
        "name": "Klaviyo campaigns summary",
        "sql": "SELECT campaign_id, report_date, sent, opens, clicks FROM public_marts.fact_klaviyo_daily "
        + _DATE_RANGE_CLAUSE
        + " ORDER BY report_date DESC, campaign_id LIMIT 50",
        "display": "table",
        "viz": {},
    },
]


def build_template_tags_date_range() -> dict:
    """Two date variables for start and end of range."""
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

    template_tags = build_template_tags_date_range()
    by_name = {q["name"]: q for q in DATE_RANGE_QUESTIONS}
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
            print(f"Updated (date range): {name} (id={card['id']})")
            updated += 1
        else:
            print(f"Failed: {name} (id={card['id']})", file=sys.stderr)

    print(
        "\nDone. Updated {} card(s).\n".format(updated)
        + "Next: Add two dashboard Date filters (Single date): 'Start date' and 'End date', then link each to its matching variable.\n"
        + "See METABASE_DATE_RANGE_SETUP.md for step-by-step instructions."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
