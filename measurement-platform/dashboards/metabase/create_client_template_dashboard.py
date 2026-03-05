#!/usr/bin/env python3
"""
Create a single Metabase template dashboard for client performance reporting.

This script builds one dashboard with the following sections:
- Executive / blended summary (12 trend cards)
- Customer metrics (5 trend cards)
- Correlation charts (sales vs spend, clicks vs spend)
- Funnel (total + platform breakdown)
- Platform breakdown (Meta, Google, TikTok; 15 trend cards each)
- Supporting views
- Experiment / GeoLift summary

Some requested metrics depend on data that is not modeled in current marts.
For those, cards are created as explicit placeholders ("pending model") so the
dashboard structure is complete and can be upgraded in-place later.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from create_mvp_dashboards import (  # noqa: E402
    METABASE_URL,
    add_card_to_dashboard,
    create_dashboard,
    get_database_id,
    get_headers,
    list_dashboards,
    login,
)

MARTS_SCHEMA = os.environ.get("MARTS_SCHEMA", "public_marts")
DASHBOARD_NAME = os.environ.get("METABASE_TEMPLATE_DASHBOARD_NAME", "Client Performance Template")
GRID_WIDTH = 12

_P1 = "{{report_date_start}}::date"
_P2 = "{{report_date_end}}::date"


@dataclass
class CardDef:
    name: str
    sql: str
    display: str
    viz: dict[str, Any]


def build_template_tags() -> dict[str, dict[str, str]]:
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
        "compare_mode": {
            "id": str(uuid.uuid4()).replace("-", "")[:8],
            "name": "compare_mode",
            "display-name": "Compare mode",
            "type": "text",
            "default": "previous_period",
        },
    }


def create_card_with_template(
    headers: dict[str, str],
    database_id: int,
    card: CardDef,
    template_tags: dict[str, dict[str, str]],
) -> dict[str, Any] | None:
    payload = {
        "name": card.name,
        "database_id": database_id,
        "dataset_query": {
            "type": "native",
            "database": database_id,
            "native": {
                "query": card.sql,
                "template-tags": template_tags,
            },
        },
        "display": card.display,
        "visualization_settings": card.viz,
    }
    response = requests.post(f"{METABASE_URL}/api/card", json=payload, headers=headers, timeout=30)
    if response.status_code not in (200, 201):
        print(f"Create card failed [{card.name}]: {response.status_code} {response.text[:250]}", file=sys.stderr)
        return None
    return response.json()


def blended_daily_sql(value_expression: str) -> str:
    return f"""
WITH spend AS (
  SELECT report_date, SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks
  FROM {MARTS_SCHEMA}.fact_spend_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
  GROUP BY report_date
),
kpi AS (
  SELECT report_date, SUM(revenue) AS revenue, SUM(orders) AS orders
  FROM {MARTS_SCHEMA}.fact_kpi_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
  GROUP BY report_date
),
dates AS (
  SELECT report_date FROM spend
  UNION
  SELECT report_date FROM kpi
)
SELECT
  d.report_date AS date,
  {value_expression} AS value
FROM dates d
LEFT JOIN spend s ON d.report_date = s.report_date
LEFT JOIN kpi k ON d.report_date = k.report_date
ORDER BY d.report_date
"""


def platform_daily_sql(channel: str, value_expression: str) -> str:
    return f"""
WITH platform AS (
  SELECT report_date, SUM(spend) AS spend, SUM(impressions) AS impressions, SUM(clicks) AS clicks
  FROM {MARTS_SCHEMA}.fact_spend_daily
  WHERE channel = '{channel}' AND report_date >= {_P1} AND report_date <= {_P2}
  GROUP BY report_date
)
SELECT
  p.report_date AS date,
  {value_expression} AS value
FROM platform p
ORDER BY p.report_date
"""


def placeholder_daily_sql() -> str:
    return f"""
WITH dates AS (
  SELECT report_date
  FROM {MARTS_SCHEMA}.fact_spend_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
  UNION
  SELECT report_date
  FROM {MARTS_SCHEMA}.fact_kpi_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
)
SELECT d.report_date AS date, NULL::numeric AS value
FROM dates d
ORDER BY d.report_date
"""


def build_executive_cards() -> list[CardDef]:
    trend_viz = {"graph.dimensions": ["date"], "graph.metrics": ["value"]}
    return [
        CardDef("Executive | MER", blended_daily_sql("ROUND((COALESCE(k.revenue, 0) / NULLIF(COALESCE(s.spend, 0), 0))::numeric, 4)"), "trend", trend_viz),
        CardDef("Executive | ROAS", blended_daily_sql("ROUND((COALESCE(k.revenue, 0) / NULLIF(COALESCE(s.spend, 0), 0))::numeric, 4)"), "trend", trend_viz),
        CardDef("Executive | LTV:CAC (pending model)", placeholder_daily_sql(), "trend", trend_viz),
        CardDef("Executive | MCPP", blended_daily_sql("ROUND((COALESCE(s.spend, 0) / NULLIF(COALESCE(k.orders, 0), 0))::numeric, 2)"), "trend", trend_viz),
        CardDef("Executive | AOV", blended_daily_sql("ROUND((COALESCE(k.revenue, 0) / NULLIF(COALESCE(k.orders, 0), 0))::numeric, 2)"), "trend", trend_viz),
        CardDef("Executive | Blended CPC", blended_daily_sql("ROUND((COALESCE(s.spend, 0) / NULLIF(COALESCE(s.clicks, 0), 0))::numeric, 2)"), "trend", trend_viz),
        CardDef("Executive | Spend", blended_daily_sql("COALESCE(s.spend, 0)::numeric"), "trend", trend_viz),
        CardDef("Executive | Revenue", blended_daily_sql("COALESCE(k.revenue, 0)::numeric"), "trend", trend_viz),
        CardDef("Executive | Orders", blended_daily_sql("COALESCE(k.orders, 0)::numeric"), "trend", trend_viz),
        CardDef("Executive | Impressions", blended_daily_sql("COALESCE(s.impressions, 0)::numeric"), "trend", trend_viz),
        CardDef("Executive | Clicks", blended_daily_sql("COALESCE(s.clicks, 0)::numeric"), "trend", trend_viz),
        CardDef("Executive | Blended Purchase Value", blended_daily_sql("ROUND((COALESCE(k.revenue, 0) / NULLIF(COALESCE(k.orders, 0), 0))::numeric, 2)"), "trend", trend_viz),
    ]


def build_customer_cards() -> list[CardDef]:
    trend_viz = {"graph.dimensions": ["date"], "graph.metrics": ["value"]}
    return [
        CardDef("Customer Metrics | Customers (proxy: orders)", blended_daily_sql("COALESCE(k.orders, 0)::numeric"), "trend", trend_viz),
        CardDef("Customer Metrics | New Customers (pending model)", placeholder_daily_sql(), "trend", trend_viz),
        CardDef("Customer Metrics | LTV (pending model)", placeholder_daily_sql(), "trend", trend_viz),
        CardDef("Customer Metrics | Avg Revenue Per Customer (proxy: AOV)", blended_daily_sql("ROUND((COALESCE(k.revenue, 0) / NULLIF(COALESCE(k.orders, 0), 0))::numeric, 2)"), "trend", trend_viz),
        CardDef("Customer Metrics | Avg Revenue Per New Customer (pending model)", placeholder_daily_sql(), "trend", trend_viz),
    ]


def build_comparison_cards() -> list[CardDef]:
    comparison_sql = f"""
WITH params AS (
  SELECT
    {_P1} AS start_date,
    {_P2} AS end_date,
    COALESCE(NULLIF(LOWER({{compare_mode}}), ''), 'previous_period') AS compare_mode
),
ranges AS (
  SELECT
    start_date,
    end_date,
    compare_mode,
    CASE
      WHEN compare_mode = 'last_year'
        THEN (start_date - INTERVAL '1 year')::date
      ELSE
        (start_date - ((end_date - start_date + 1) * INTERVAL '1 day'))::date
    END AS compare_start_date,
    CASE
      WHEN compare_mode = 'last_year'
        THEN (end_date - INTERVAL '1 year')::date
      ELSE
        (start_date - INTERVAL '1 day')::date
    END AS compare_end_date
  FROM params
),
kpi AS (
  SELECT
    SUM(CASE WHEN k.report_date BETWEEN r.start_date AND r.end_date THEN k.revenue ELSE 0 END) AS cur_revenue,
    SUM(CASE WHEN k.report_date BETWEEN r.compare_start_date AND r.compare_end_date THEN k.revenue ELSE 0 END) AS prior_revenue,
    SUM(CASE WHEN k.report_date BETWEEN r.start_date AND r.end_date THEN k.orders ELSE 0 END) AS cur_orders,
    SUM(CASE WHEN k.report_date BETWEEN r.compare_start_date AND r.compare_end_date THEN k.orders ELSE 0 END) AS prior_orders
  FROM {MARTS_SCHEMA}.fact_kpi_daily k
  CROSS JOIN ranges r
  WHERE k.report_date BETWEEN LEAST(r.start_date, r.compare_start_date) AND GREATEST(r.end_date, r.compare_end_date)
),
spend AS (
  SELECT
    SUM(CASE WHEN s.report_date BETWEEN r.start_date AND r.end_date THEN s.spend ELSE 0 END) AS cur_spend,
    SUM(CASE WHEN s.report_date BETWEEN r.compare_start_date AND r.compare_end_date THEN s.spend ELSE 0 END) AS prior_spend,
    SUM(CASE WHEN s.report_date BETWEEN r.start_date AND r.end_date THEN s.impressions ELSE 0 END) AS cur_impressions,
    SUM(CASE WHEN s.report_date BETWEEN r.compare_start_date AND r.compare_end_date THEN s.impressions ELSE 0 END) AS prior_impressions,
    SUM(CASE WHEN s.report_date BETWEEN r.start_date AND r.end_date THEN s.clicks ELSE 0 END) AS cur_clicks,
    SUM(CASE WHEN s.report_date BETWEEN r.compare_start_date AND r.compare_end_date THEN s.clicks ELSE 0 END) AS prior_clicks
  FROM {MARTS_SCHEMA}.fact_spend_daily s
  CROSS JOIN ranges r
  WHERE s.report_date BETWEEN LEAST(r.start_date, r.compare_start_date) AND GREATEST(r.end_date, r.compare_end_date)
),
ranges_out AS (
  SELECT
    compare_mode,
    start_date,
    end_date,
    compare_start_date,
    compare_end_date
  FROM ranges
)
SELECT
  'Spend'::text AS metric,
  ROUND(COALESCE(s.cur_spend, 0)::numeric, 2) AS current_value,
  ROUND(COALESCE(s.prior_spend, 0)::numeric, 2) AS comparison_value,
  CASE WHEN COALESCE(s.prior_spend, 0) = 0 THEN 0
       ELSE ROUND(((s.cur_spend - s.prior_spend) / s.prior_spend * 100)::numeric, 1) END AS pct_change,
  r.compare_mode,
  r.start_date,
  r.end_date,
  r.compare_start_date,
  r.compare_end_date
FROM spend s CROSS JOIN ranges_out r
UNION ALL
SELECT
  'Revenue',
  ROUND(COALESCE(k.cur_revenue, 0)::numeric, 2),
  ROUND(COALESCE(k.prior_revenue, 0)::numeric, 2),
  CASE WHEN COALESCE(k.prior_revenue, 0) = 0 THEN 0
       ELSE ROUND(((k.cur_revenue - k.prior_revenue) / k.prior_revenue * 100)::numeric, 1) END,
  r.compare_mode, r.start_date, r.end_date, r.compare_start_date, r.compare_end_date
FROM kpi k CROSS JOIN ranges_out r
UNION ALL
SELECT
  'Orders',
  ROUND(COALESCE(k.cur_orders, 0)::numeric, 2),
  ROUND(COALESCE(k.prior_orders, 0)::numeric, 2),
  CASE WHEN COALESCE(k.prior_orders, 0) = 0 THEN 0
       ELSE ROUND(((k.cur_orders - k.prior_orders) / k.prior_orders * 100)::numeric, 1) END,
  r.compare_mode, r.start_date, r.end_date, r.compare_start_date, r.compare_end_date
FROM kpi k CROSS JOIN ranges_out r
UNION ALL
SELECT
  'ROAS',
  ROUND((CASE WHEN COALESCE(s.cur_spend, 0) = 0 THEN 0 ELSE k.cur_revenue / NULLIF(s.cur_spend, 0) END)::numeric, 3),
  ROUND((CASE WHEN COALESCE(s.prior_spend, 0) = 0 THEN 0 ELSE k.prior_revenue / NULLIF(s.prior_spend, 0) END)::numeric, 3),
  CASE
    WHEN COALESCE(s.prior_spend, 0) = 0 OR COALESCE(k.prior_revenue, 0) = 0 THEN 0
    ELSE ROUND((((k.cur_revenue / NULLIF(s.cur_spend, 0)) - (k.prior_revenue / NULLIF(s.prior_spend, 0)))
         / NULLIF((k.prior_revenue / NULLIF(s.prior_spend, 0)), 0) * 100)::numeric, 1)
  END,
  r.compare_mode, r.start_date, r.end_date, r.compare_start_date, r.compare_end_date
FROM kpi k CROSS JOIN spend s CROSS JOIN ranges_out r
ORDER BY metric
"""
    return [CardDef("Executive Comparison | Current vs Comparison", comparison_sql, "table", {})]


def build_correlation_cards() -> list[CardDef]:
    sales_vs_spend_sql = f"""
WITH spend AS (
  SELECT report_date, SUM(spend) AS spend
  FROM {MARTS_SCHEMA}.fact_spend_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
  GROUP BY report_date
),
kpi AS (
  SELECT report_date, SUM(revenue) AS revenue
  FROM {MARTS_SCHEMA}.fact_kpi_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
  GROUP BY report_date
)
SELECT
  COALESCE(k.report_date, s.report_date) AS date,
  COALESCE(s.spend, 0)::numeric AS spend,
  COALESCE(k.revenue, 0)::numeric AS revenue
FROM kpi k
FULL OUTER JOIN spend s ON k.report_date = s.report_date
ORDER BY date
"""
    clicks_vs_spend_sql = f"""
WITH spend AS (
  SELECT report_date, SUM(spend) AS spend, SUM(clicks) AS clicks
  FROM {MARTS_SCHEMA}.fact_spend_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
  GROUP BY report_date
)
SELECT
  report_date AS date,
  COALESCE(spend, 0)::numeric AS spend,
  COALESCE(clicks, 0)::numeric AS clicks
FROM spend
ORDER BY report_date
"""
    return [
        CardDef(
            "Correlation | Sales vs Spend",
            sales_vs_spend_sql,
            "line",
            {"graph.dimensions": ["date"], "graph.metrics": ["spend", "revenue"]},
        ),
        CardDef(
            "Correlation | Clicks vs Spend",
            clicks_vs_spend_sql,
            "line",
            {"graph.dimensions": ["date"], "graph.metrics": ["spend", "clicks"]},
        ),
    ]


def build_funnel_cards() -> list[CardDef]:
    total_funnel_sql = f"""
WITH spend AS (
  SELECT SUM(impressions) AS impressions, SUM(clicks) AS clicks
  FROM {MARTS_SCHEMA}.fact_spend_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
),
kpi AS (
  SELECT SUM(orders) AS orders
  FROM {MARTS_SCHEMA}.fact_kpi_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
)
SELECT 'Impressions' AS stage, COALESCE(s.impressions, 0)::numeric AS value FROM spend s
UNION ALL
SELECT 'Clicks' AS stage, COALESCE(s.clicks, 0)::numeric AS value FROM spend s
UNION ALL
SELECT 'Orders' AS stage, COALESCE(k.orders, 0)::numeric AS value FROM kpi k
"""
    stage_rates_sql = f"""
WITH spend AS (
  SELECT SUM(impressions) AS impressions, SUM(clicks) AS clicks
  FROM {MARTS_SCHEMA}.fact_spend_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
),
kpi AS (
  SELECT SUM(orders) AS orders
  FROM {MARTS_SCHEMA}.fact_kpi_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
)
SELECT
  COALESCE(s.impressions, 0)::numeric AS impressions,
  COALESCE(s.clicks, 0)::numeric AS clicks,
  COALESCE(k.orders, 0)::numeric AS orders,
  ROUND((COALESCE(s.clicks, 0)::numeric / NULLIF(COALESCE(s.impressions, 0), 0) * 100), 2) AS click_through_rate_pct,
  ROUND((COALESCE(k.orders, 0)::numeric / NULLIF(COALESCE(s.clicks, 0), 0) * 100), 2) AS click_to_order_rate_pct
FROM spend s
CROSS JOIN kpi k
"""
    platform_funnel_sql = f"""
SELECT
  channel,
  SUM(impressions)::numeric AS impressions,
  SUM(clicks)::numeric AS clicks,
  ROUND((SUM(clicks)::numeric / NULLIF(SUM(impressions), 0) * 100), 2) AS ctr_pct,
  ROUND((SUM(spend)::numeric / NULLIF(SUM(clicks), 0)), 2) AS cpc
FROM {MARTS_SCHEMA}.fact_spend_daily
WHERE report_date >= {_P1} AND report_date <= {_P2}
GROUP BY channel
ORDER BY SUM(spend) DESC
"""
    return [
        CardDef("Funnel | Total Funnel", total_funnel_sql, "bar", {"graph.dimensions": ["stage"], "graph.metrics": ["value"]}),
        CardDef("Funnel | Stage Conversion Rates", stage_rates_sql, "table", {}),
        CardDef("Funnel | Platform Funnel Breakdown", platform_funnel_sql, "table", {}),
    ]


def platform_metric_cards(channel: str, label: str) -> list[CardDef]:
    trend_viz = {"graph.dimensions": ["date"], "graph.metrics": ["value"]}
    return [
        CardDef(f"{label} | Spend", platform_daily_sql(channel, "COALESCE(p.spend, 0)::numeric"), "trend", trend_viz),
        CardDef(f"{label} | Impressions", platform_daily_sql(channel, "COALESCE(p.impressions, 0)::numeric"), "trend", trend_viz),
        CardDef(f"{label} | CPM", platform_daily_sql(channel, "ROUND(((COALESCE(p.spend, 0) / NULLIF(COALESCE(p.impressions, 0), 0)) * 1000)::numeric, 2)"), "trend", trend_viz),
        CardDef(f"{label} | Unique Outbound Clicks (proxy: clicks)", platform_daily_sql(channel, "COALESCE(p.clicks, 0)::numeric"), "trend", trend_viz),
        CardDef(f"{label} | Unique Outbound CTR (proxy)", platform_daily_sql(channel, "ROUND((COALESCE(p.clicks, 0)::numeric / NULLIF(COALESCE(p.impressions, 0), 0) * 100), 2)"), "trend", trend_viz),
        CardDef(f"{label} | Unique Cost Per Outbound Click (proxy)", platform_daily_sql(channel, "ROUND((COALESCE(p.spend, 0) / NULLIF(COALESCE(p.clicks, 0), 0))::numeric, 2)"), "trend", trend_viz),
        CardDef(f"{label} | Cost Per Add To Cart (pending model)", placeholder_daily_sql(), "trend", trend_viz),
        CardDef(f"{label} | Cost Per Checkout (pending model)", placeholder_daily_sql(), "trend", trend_viz),
        CardDef(f"{label} | Cost Per Purchase (pending attributed orders)", placeholder_daily_sql(), "trend", trend_viz),
        CardDef(f"{label} | ROAS (pending attributed revenue)", placeholder_daily_sql(), "trend", trend_viz),
        CardDef(f"{label} | Frequency (pending model)", placeholder_daily_sql(), "trend", trend_viz),
        CardDef(f"{label} | AOV (pending attributed orders)", placeholder_daily_sql(), "trend", trend_viz),
        CardDef(f"{label} | CVR (pending attributed orders)", placeholder_daily_sql(), "trend", trend_viz),
        CardDef(f"{label} | Hook Ratio (pending model)", placeholder_daily_sql(), "trend", trend_viz),
        CardDef(f"{label} | Hold Rate (pending model)", placeholder_daily_sql(), "trend", trend_viz),
    ]


def build_supporting_cards() -> list[CardDef]:
    spend_share_sql = f"""
SELECT
  channel,
  SUM(spend)::numeric AS spend
FROM {MARTS_SCHEMA}.fact_spend_daily
WHERE report_date >= {_P1} AND report_date <= {_P2}
GROUP BY channel
ORDER BY SUM(spend) DESC
"""
    roas_by_platform_pending_sql = f"""
WITH platform_dates AS (
  SELECT report_date, channel
  FROM {MARTS_SCHEMA}.fact_spend_daily
  WHERE report_date >= {_P1} AND report_date <= {_P2}
  GROUP BY report_date, channel
)
SELECT
  report_date AS date,
  channel,
  NULL::numeric AS roas
FROM platform_dates
ORDER BY report_date, channel
"""
    return [
        CardDef("Supporting | Spend Share by Platform", spend_share_sql, "pie", {"pie.dimension": "channel", "pie.metric": "spend"}),
        CardDef(
            "Supporting | ROAS by Platform Over Time (pending attributed revenue)",
            roas_by_platform_pending_sql,
            "line",
            {"graph.dimensions": ["date", "channel"], "graph.metrics": ["roas"]},
        ),
    ]


def build_experiment_cards() -> list[CardDef]:
    active_tests_sql = """
SELECT
  COUNT(*)::numeric AS active_geolift_tests
FROM public.experiments
WHERE LOWER(experiment_type) = 'geolift'
  AND LOWER(status) IN ('running', 'active', 'in_progress')
"""
    latest_summary_sql = """
WITH latest AS (
  SELECT
    r.experiment_id,
    r.metric,
    r.value,
    r.interval_lower,
    r.interval_upper,
    r.result_date,
    ROW_NUMBER() OVER (PARTITION BY r.experiment_id, r.metric ORDER BY r.result_date DESC) AS rn
  FROM public.experiment_results r
),
geolift AS (
  SELECT id, experiment_slug, status, start_date, end_date
  FROM public.experiments
  WHERE LOWER(experiment_type) = 'geolift'
)
SELECT
  g.experiment_slug,
  g.status,
  g.start_date,
  g.end_date,
  l.metric,
  l.value,
  l.interval_lower,
  l.interval_upper,
  l.result_date
FROM geolift g
LEFT JOIN latest l ON l.experiment_id = g.id AND l.rn = 1
ORDER BY g.end_date DESC NULLS LAST, g.start_date DESC NULLS LAST
"""
    lift_over_time_sql = """
SELECT
  e.experiment_slug,
  r.result_date AS date,
  r.metric,
  r.value,
  r.interval_lower,
  r.interval_upper
FROM public.experiment_results r
JOIN public.experiments e ON e.id = r.experiment_id
WHERE LOWER(e.experiment_type) = 'geolift'
ORDER BY e.experiment_slug, r.result_date
"""
    return [
        CardDef("Experiments | Active GeoLift Tests", active_tests_sql, "scalar", {}),
        CardDef("Experiments | Latest GeoLift Summary", latest_summary_sql, "table", {}),
        CardDef("Experiments | GeoLift Lift Over Time", lift_over_time_sql, "line", {"graph.dimensions": ["date", "experiment_slug"], "graph.metrics": ["value"]}),
    ]


def build_dashboard_sections() -> list[dict[str, Any]]:
    return [
        {"name": "Executive / Blended Summary", "cards": build_executive_cards(), "size_x": 2, "size_y": 3},
        {"name": "Customer Metrics", "cards": build_customer_cards(), "size_x": 2, "size_y": 3},
        {"name": "Executive Comparison", "cards": build_comparison_cards(), "size_x": 12, "size_y": 4},
        {"name": "Correlation Charts", "cards": build_correlation_cards(), "size_x": 12, "size_y": 4},
        {"name": "Funnel", "cards": build_funnel_cards(), "size_x": 12, "size_y": 4},
        {"name": "Platform Breakdown | Meta", "cards": platform_metric_cards("meta", "Meta"), "size_x": 2, "size_y": 3},
        {"name": "Platform Breakdown | Google", "cards": platform_metric_cards("google", "Google"), "size_x": 2, "size_y": 3},
        {"name": "Platform Breakdown | TikTok", "cards": platform_metric_cards("tiktok", "TikTok"), "size_x": 2, "size_y": 3},
        {"name": "Supporting Views", "cards": build_supporting_cards(), "size_x": 12, "size_y": 4},
        {"name": "Experiment / GeoLift Snapshot", "cards": build_experiment_cards(), "size_x": 12, "size_y": 4},
    ]


def print_dry_run_summary(sections: list[dict[str, Any]]) -> None:
    total_cards = 0
    print(f"Dashboard dry run: {DASHBOARD_NAME}")
    print(f"Metabase URL: {METABASE_URL}")
    print(f"Marts schema: {MARTS_SCHEMA}")
    for section in sections:
        count = len(section["cards"])
        total_cards += count
        print(f"  - {section['name']}: {count} cards")
    print(f"Total cards: {total_cards}")


def place_section_cards(
    headers: dict[str, str],
    database_id: int,
    dashboard_id: int,
    template_tags: dict[str, dict[str, str]],
    section: dict[str, Any],
    row_start: int,
) -> int:
    cards: list[CardDef] = section["cards"]
    size_x = int(section["size_x"])
    size_y = int(section["size_y"])

    print(f"\nSection: {section['name']} ({len(cards)} cards)")

    row = row_start
    col = 0
    for card in cards:
        created = create_card_with_template(headers, database_id, card, template_tags)
        if created is None:
            continue
        added = add_card_to_dashboard(
            headers,
            dashboard_id,
            created["id"],
            row=row,
            col=col,
            size_x=size_x,
            size_y=size_y,
        )
        if added:
            print(f"  Added: {card.name}")
        else:
            print(f"  Card created but not placed: {card.name}", file=sys.stderr)

        col += size_x
        if col >= GRID_WIDTH:
            col = 0
            row += size_y

    if col != 0:
        row += size_y
    return row


def find_dashboard_id_by_name(headers: dict[str, str], name: str) -> int | None:
    for dashboard in list_dashboards(headers):
        if dashboard.get("name") == name:
            return dashboard.get("id")
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the client dashboard template in Metabase.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned sections/cards without calling Metabase APIs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sections = build_dashboard_sections()
    if args.dry_run:
        print_dry_run_summary(sections)
        return 0

    session_id = login()
    if session_id is None:
        return 1
    headers = get_headers(session_id)

    db_id = get_database_id(headers)
    if not db_id:
        print("No Metabase database found. Add the client warehouse DB first.", file=sys.stderr)
        return 1

    existing = find_dashboard_id_by_name(headers, DASHBOARD_NAME)
    if existing:
        print(f"Dashboard already exists: {DASHBOARD_NAME} (id={existing})")
        print(f"  -> {METABASE_URL}/dashboard/{existing}")
        print("Delete the existing dashboard in Metabase if you want to recreate it.")
        return 0

    dashboard = create_dashboard(headers, DASHBOARD_NAME)
    if not dashboard:
        return 1
    dashboard_id = dashboard["id"]
    print(f"Created dashboard: {DASHBOARD_NAME} (id={dashboard_id})")

    template_tags = build_template_tags()
    row = 0
    for section in sections:
        row = place_section_cards(headers, db_id, dashboard_id, template_tags, section, row)

    print(f"\nDone. Open: {METABASE_URL}/dashboard/{dashboard_id}")
    print("Add dashboard filters in Metabase UI:")
    print("  - Start date (map to report_date_start)")
    print("  - End date (map to report_date_end)")
    print("  - Compare mode (map to compare_mode; use values: previous_period or last_year)")
    print("  - Optional channel filter for section-specific cards")
    print("Cards marked '(pending model)' are placeholders for metrics that require additional marts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
