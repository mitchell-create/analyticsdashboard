#!/usr/bin/env python3
"""
Apply Option B: add report_date + period (Day|Week|Month) to all cards so the
dashboard can filter by day, week, or month. Date filter = "Single date";
add a second filter (Category/Dropdown) for Period with options Day, Week, Month.

Run after Metabase is connected. Same env as create_mvp_dashboards.py.
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

# Date range clause: Day = that date; Week = Mon–Sun containing date (ISO week); Month = calendar month.
# Uses report_date (single date) + period (Day|Week|Month). [[...]] = optional.
_DATE_RANGE_CLAUSE = """[[WHERE (
  ({{period}} = 'Day' AND report_date = ({{report_date}})::date)
  OR ({{period}} = 'Week' AND report_date >= (date_trunc('week', ({{report_date}})::timestamp))::date AND report_date < (date_trunc('week', ({{report_date}})::timestamp))::date + 7)
  OR ({{period}} = 'Month' AND report_date >= (date_trunc('month', ({{report_date}})::timestamp))::date AND report_date < ((date_trunc('month', ({{report_date}})::timestamp))::date + interval '1 month')::date)
)]]"""
_AND_DATE_RANGE = """[[AND (
  ({{period}} = 'Day' AND report_date = ({{report_date}})::date)
  OR ({{period}} = 'Week' AND report_date >= (date_trunc('week', ({{report_date}})::timestamp))::date AND report_date < (date_trunc('week', ({{report_date}})::timestamp))::date + 7)
  OR ({{period}} = 'Month' AND report_date >= (date_trunc('month', ({{report_date}})::timestamp))::date AND report_date < ((date_trunc('month', ({{report_date}})::timestamp))::date + interval '1 month')::date)
)]]"""
_AND_S_DATE_RANGE = """[[AND (
  ({{period}} = 'Day' AND s.report_date = ({{report_date}})::date)
  OR ({{period}} = 'Week' AND s.report_date >= (date_trunc('week', ({{report_date}})::timestamp))::date AND s.report_date < (date_trunc('week', ({{report_date}})::timestamp))::date + 7)
  OR ({{period}} = 'Month' AND s.report_date >= (date_trunc('month', ({{report_date}})::timestamp))::date AND s.report_date < ((date_trunc('month', ({{report_date}})::timestamp))::date + interval '1 month')::date)
)]]"""

OPTION_B_QUESTIONS = [
    {
        "name": "Daily revenue",
        "sql": "SELECT report_date AS date, COALESCE(SUM(revenue), 0) AS revenue FROM public_marts.fact_kpi_daily " + _DATE_RANGE_CLAUSE + " GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["revenue"]},
    },
    {
        "name": "Daily orders",
        "sql": "SELECT report_date AS date, COALESCE(SUM(orders), 0) AS orders FROM public_marts.fact_kpi_daily " + _DATE_RANGE_CLAUSE + " GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["orders"]},
    },
    {
        "name": "Spend by date",
        "sql": "SELECT report_date AS date, COALESCE(SUM(spend), 0) AS spend FROM public_marts.fact_spend_daily " + _DATE_RANGE_CLAUSE + " GROUP BY report_date ORDER BY report_date",
        "display": "line",
        "viz": {"graph.dimensions": ["date"], "graph.metrics": ["spend"]},
    },
    {
        "name": "Total spend by channel",
        "sql": "SELECT channel, COALESCE(SUM(spend), 0) AS spend FROM public_marts.fact_spend_daily " + _DATE_RANGE_CLAUSE + " GROUP BY channel ORDER BY spend DESC",
        "display": "bar",
        "viz": {"graph.dimensions": ["channel"], "graph.metrics": ["spend"]},
    },
    {
        "name": "ROAS (revenue / spend)",
        "sql": """SELECT
  (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily WHERE 1=1 """ + _AND_DATE_RANGE + """) AS revenue,
  (SELECT COALESCE(SUM(spend), 0) FROM public_marts.fact_spend_daily WHERE 1=1 """ + _AND_DATE_RANGE + """) AS spend,
  CASE WHEN (SELECT COALESCE(SUM(spend), 0) FROM public_marts.fact_spend_daily WHERE 1=1 """ + _AND_DATE_RANGE + """) = 0 THEN 0
       ELSE (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily WHERE 1=1 """ + _AND_DATE_RANGE + """)
            / NULLIF((SELECT SUM(spend) FROM public_marts.fact_spend_daily WHERE 1=1 """ + _AND_DATE_RANGE + """), 0) END AS roas""",
        "display": "table",
        "viz": {},
    },
    {
        "name": "Spend by channel over time",
        "sql": "SELECT report_date AS date, channel, COALESCE(SUM(spend), 0) AS spend FROM public_marts.fact_spend_daily " + _DATE_RANGE_CLAUSE + " GROUP BY report_date, channel ORDER BY report_date, channel",
        "display": "line",
        "viz": {"graph.dimensions": ["date", "channel"], "graph.metrics": ["spend"]},
    },
    {
        "name": "ROAS by channel",
        "sql": """SELECT s.channel,
  COALESCE(SUM(s.spend), 0) AS spend,
  (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily WHERE 1=1 """ + _AND_DATE_RANGE + """) AS revenue,
  CASE WHEN SUM(s.spend) = 0 THEN 0 ELSE (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily WHERE 1=1 """ + _AND_DATE_RANGE + """) / NULLIF(SUM(s.spend), 0) END AS roas
FROM public_marts.fact_spend_daily s
WHERE 1=1 """ + _AND_S_DATE_RANGE + """
GROUP BY s.channel
ORDER BY spend DESC""",
        "display": "table",
        "viz": {},
    },
    {
        "name": "Impressions and clicks by channel",
        "sql": "SELECT report_date AS date, channel, SUM(impressions) AS impressions, SUM(clicks) AS clicks FROM public_marts.fact_spend_daily " + _DATE_RANGE_CLAUSE + " GROUP BY report_date, channel ORDER BY report_date, channel",
        "display": "line",
        "viz": {"graph.dimensions": ["date", "channel"], "graph.metrics": ["impressions", "clicks"]},
    },
    {
        "name": "Spend share by channel",
        "sql": "SELECT channel, COALESCE(SUM(spend), 0) AS spend FROM public_marts.fact_spend_daily " + _DATE_RANGE_CLAUSE + " GROUP BY channel ORDER BY spend DESC",
        "display": "pie",
        "viz": {"pie.dimension": "channel", "pie.metric": "spend"},
    },
]


def build_template_tags_date_and_period() -> dict:
    """report_date (single date) + period (Day|Week|Month) so dashboard can filter by day, week, or month."""
    return {
        "report_date": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "report_date",
            "display-name": "Report date",
            "type": "date",
        },
        "period": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "period",
            "display-name": "Period",
            "type": "text",
            "default": "Day",
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

    template_tags = build_template_tags_date_and_period()
    by_name = {q["name"]: q for q in OPTION_B_QUESTIONS}
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
            print(f"Updated (Option B): {name} (id={card['id']})")
            updated += 1
        else:
            print(f"Failed: {name} (id={card['id']})", file=sys.stderr)

    print(
        "\nDone. Updated {0} card(s). Add two dashboard filters: (1) Date = 'Single date', link to 'Report date'; "
        "(2) Category/Dropdown 'Period' with options Day, Week, Month, link to 'Period'. Pick a date + Period to filter by day, week, or month.".format(updated)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
