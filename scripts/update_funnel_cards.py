"""Update existing funnel cards (322, 323) to incorporate GA4 data."""
import requests
import json

MB_URL = "http://localhost:3000"
MB_KEY = "mb_shG81kdEkgdKIR7njalW+w2SIvEk8sAygAPT6vIyze0="
HEADERS = {"x-api-key": MB_KEY, "Content-Type": "application/json"}


def update_card_sql(card_id, new_sql, new_name=None):
    r = requests.get(f"{MB_URL}/api/card/{card_id}", headers=HEADERS)
    r.raise_for_status()
    card = r.json()
    dq = card["dataset_query"]
    if "stages" in dq:
        dq["stages"][0]["native"] = new_sql
    elif "native" in dq:
        dq["native"]["query"] = new_sql
    payload = {"dataset_query": dq}
    if new_name:
        payload["name"] = new_name
    r = requests.put(f"{MB_URL}/api/card/{card_id}", headers=HEADERS, json=payload)
    r.raise_for_status()
    print(f"[OK] Card {card_id} updated -> {new_name or card.get('name')}")


# ==========================================
# Card 322: Total Funnel - add GA4 web stages
# ==========================================
FUNNEL_SQL = """WITH ga4 AS (
  SELECT
    SUM(sessions) AS sessions,
    SUM(product_views) AS product_views,
    SUM(add_to_carts) AS add_to_carts,
    SUM(checkouts) AS checkouts,
    SUM(purchases) AS ga4_purchases
  FROM public_marts.fact_ga4_funnel_daily
  WHERE client_slug = {{client_slug}}
    AND report_date >= {{report_date_start}}::date AND report_date <= {{report_date_end}}::date
),
spend AS (
  SELECT SUM(clicks) AS clicks
  FROM public_marts.fact_spend_daily_fx
  WHERE client_slug = {{client_slug}}
    AND report_date >= {{report_date_start}}::date AND report_date <= {{report_date_end}}::date
),
kpi AS (
  SELECT SUM(orders) AS orders
  FROM public_marts.fact_kpi_daily
  WHERE client_slug = {{client_slug}}
    AND report_date >= {{report_date_start}}::date AND report_date <= {{report_date_end}}::date
)
SELECT stage, value FROM (
  SELECT 1 AS sort, 'Sessions' AS stage, COALESCE(g.sessions, 0)::numeric AS value FROM ga4 g
  UNION ALL
  SELECT 2, 'Product Views', COALESCE(g.product_views, 0)::numeric FROM ga4 g
  UNION ALL
  SELECT 3, 'Ad Clicks', COALESCE(s.clicks, 0)::numeric FROM spend s
  UNION ALL
  SELECT 4, 'Add to Cart', COALESCE(g.add_to_carts, 0)::numeric FROM ga4 g
  UNION ALL
  SELECT 5, 'Checkout', COALESCE(g.checkouts, 0)::numeric FROM ga4 g
  UNION ALL
  SELECT 6, 'Orders', COALESCE(k.orders, 0)::numeric FROM kpi k
) sub
ORDER BY sort"""

update_card_sql(322, FUNNEL_SQL, "Total Funnel")


# ==========================================
# Card 323: Stage Conversion Rates - add GA4 rates
# ==========================================
RATES_SQL = """WITH ga4 AS (
  SELECT
    SUM(sessions) AS sessions,
    SUM(product_views) AS product_views,
    SUM(add_to_carts) AS add_to_carts,
    SUM(checkouts) AS checkouts,
    SUM(purchases) AS ga4_purchases
  FROM public_marts.fact_ga4_funnel_daily
  WHERE client_slug = {{client_slug}}
    AND report_date >= {{report_date_start}}::date AND report_date <= {{report_date_end}}::date
),
spend AS (
  SELECT SUM(impressions) AS impressions, SUM(clicks) AS clicks
  FROM public_marts.fact_spend_daily_fx
  WHERE client_slug = {{client_slug}}
    AND report_date >= {{report_date_start}}::date AND report_date <= {{report_date_end}}::date
),
kpi AS (
  SELECT SUM(orders) AS orders
  FROM public_marts.fact_kpi_daily
  WHERE client_slug = {{client_slug}}
    AND report_date >= {{report_date_start}}::date AND report_date <= {{report_date_end}}::date
)
SELECT
  COALESCE(g.sessions, 0)::numeric AS "Sessions",
  COALESCE(s.impressions, 0)::numeric AS "Impressions",
  COALESCE(s.clicks, 0)::numeric AS "Ad Clicks",
  COALESCE(g.add_to_carts, 0)::numeric AS "Add to Carts",
  COALESCE(g.checkouts, 0)::numeric AS "Checkouts",
  COALESCE(k.orders, 0)::numeric AS "Orders",
  ROUND((s.clicks * 100.0 / NULLIF(s.impressions, 0))::numeric, 2) || '%' AS "CTR",
  ROUND((g.add_to_carts * 100.0 / NULLIF(g.sessions, 0))::numeric, 2) || '%' AS "Session→ATC",
  ROUND((g.checkouts * 100.0 / NULLIF(g.add_to_carts, 0))::numeric, 1) || '%' AS "ATC→Checkout",
  ROUND((k.orders * 100.0 / NULLIF(g.checkouts, 0))::numeric, 1) || '%' AS "Checkout→Order",
  ROUND((k.orders * 100.0 / NULLIF(g.sessions, 0))::numeric, 3) || '%' AS "Overall CVR"
FROM ga4 g, spend s, kpi k"""

update_card_sql(323, RATES_SQL, "Stage Conversion Rates")


print("\n[OK] Funnel cards updated with GA4 data!")
