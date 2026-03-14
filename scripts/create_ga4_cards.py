"""Create GA4 web analytics cards and update funnel cards on Dashboard 131."""
import requests
import json

MB_URL = "http://localhost:3000"
MB_KEY = "mb_shG81kdEkgdKIR7njalW+w2SIvEk8sAygAPT6vIyze0="
HEADERS = {"x-api-key": MB_KEY, "Content-Type": "application/json"}
DB_ID = 2  # Supabase database ID in Metabase
COLLECTION_ID = None  # Will use root collection

# First, figure out what collection the other cards use
r = requests.get(f"{MB_URL}/api/card/335", headers=HEADERS)
r.raise_for_status()
COLLECTION_ID = r.json().get("collection_id")
print(f"Using collection_id: {COLLECTION_ID}")


def create_smart_scalar_card(name, sql, template_tags):
    """Create a new smart scalar Metabase card."""
    payload = {
        "name": name,
        "display": "smartscalar",
        "dataset_query": {
            "database": DB_ID,
            "type": "native",
            "native": {
                "query": sql,
                "template-tags": template_tags
            }
        },
        "visualization_settings": {
            "graph.dimensions": ["date"],
            "graph.metrics": ["value"]
        },
        "collection_id": COLLECTION_ID
    }
    r = requests.post(f"{MB_URL}/api/card", headers=HEADERS, json=payload)
    r.raise_for_status()
    card = r.json()
    print(f"[OK] Created card {card['id']}: {name}")
    return card["id"]


def create_chart_card(name, display, sql, template_tags, viz_settings=None):
    """Create a new chart Metabase card."""
    payload = {
        "name": name,
        "display": display,
        "dataset_query": {
            "database": DB_ID,
            "type": "native",
            "native": {
                "query": sql,
                "template-tags": template_tags
            }
        },
        "visualization_settings": viz_settings or {},
        "collection_id": COLLECTION_ID
    }
    r = requests.post(f"{MB_URL}/api/card", headers=HEADERS, json=payload)
    r.raise_for_status()
    card = r.json()
    print(f"[OK] Created card {card['id']}: {name}")
    return card["id"]


# Standard template tags for all cards
TEMPLATE_TAGS = {
    "compare_mode": {
        "type": "text",
        "id": "cmp_ga4",
        "name": "compare_mode",
        "display-name": "Compare mode",
        "default": "previous_period"
    },
    "report_date_start": {
        "display-name": "Start date",
        "id": "rds_ga4",
        "name": "report_date_start",
        "type": "date"
    },
    "report_date_end": {
        "display-name": "End date",
        "id": "rde_ga4",
        "name": "report_date_end",
        "type": "date"
    },
    "client_slug": {
        "type": "text",
        "id": "cs_ga4",
        "name": "client_slug",
        "display-name": "Client",
        "default": "expand"
    }
}


# ==========================================
# 1. GA4 Sessions (smart scalar)
# ==========================================
SESSIONS_SQL = """WITH params AS (
  SELECT {{report_date_start}}::date AS s, {{report_date_end}}::date AS e,
         ({{report_date_end}}::date - {{report_date_start}}::date + 1) AS days,
         {{compare_mode}} AS cmp
),
comp AS (
  SELECT
    CASE WHEN cmp = 'previous_year' THEN (s - INTERVAL '1 year')::date ELSE s - days END AS cs,
    CASE WHEN cmp = 'previous_year' THEN (e - INTERVAL '1 year')::date ELSE s - 1 END AS ce
  FROM params
)
SELECT (SELECT ce FROM comp) AS date,
  COALESCE(SUM(f.sessions), 0)::numeric AS value
FROM public_marts.fact_ga4_funnel_daily f
WHERE f.client_slug = {{client_slug}}
  AND f.report_date >= (SELECT cs FROM comp) AND f.report_date <= (SELECT ce FROM comp)
UNION ALL
SELECT (SELECT e FROM params) AS date,
  COALESCE(SUM(f.sessions), 0)::numeric AS value
FROM public_marts.fact_ga4_funnel_daily f
WHERE f.client_slug = {{client_slug}}
  AND f.report_date >= (SELECT s FROM params) AND f.report_date <= (SELECT e FROM params)
ORDER BY date"""

sessions_id = create_smart_scalar_card("Web Sessions", SESSIONS_SQL, TEMPLATE_TAGS)


# ==========================================
# 2. GA4 Add to Carts (smart scalar)
# ==========================================
ATC_SQL = """WITH params AS (
  SELECT {{report_date_start}}::date AS s, {{report_date_end}}::date AS e,
         ({{report_date_end}}::date - {{report_date_start}}::date + 1) AS days,
         {{compare_mode}} AS cmp
),
comp AS (
  SELECT
    CASE WHEN cmp = 'previous_year' THEN (s - INTERVAL '1 year')::date ELSE s - days END AS cs,
    CASE WHEN cmp = 'previous_year' THEN (e - INTERVAL '1 year')::date ELSE s - 1 END AS ce
  FROM params
)
SELECT (SELECT ce FROM comp) AS date,
  COALESCE(SUM(f.add_to_carts), 0)::numeric AS value
FROM public_marts.fact_ga4_funnel_daily f
WHERE f.client_slug = {{client_slug}}
  AND f.report_date >= (SELECT cs FROM comp) AND f.report_date <= (SELECT ce FROM comp)
UNION ALL
SELECT (SELECT e FROM params) AS date,
  COALESCE(SUM(f.add_to_carts), 0)::numeric AS value
FROM public_marts.fact_ga4_funnel_daily f
WHERE f.client_slug = {{client_slug}}
  AND f.report_date >= (SELECT s FROM params) AND f.report_date <= (SELECT e FROM params)
ORDER BY date"""

atc_id = create_smart_scalar_card("Web Add to Carts", ATC_SQL, TEMPLATE_TAGS)


# ==========================================
# 3. GA4 Checkouts (smart scalar)
# ==========================================
CHECKOUT_SQL = """WITH params AS (
  SELECT {{report_date_start}}::date AS s, {{report_date_end}}::date AS e,
         ({{report_date_end}}::date - {{report_date_start}}::date + 1) AS days,
         {{compare_mode}} AS cmp
),
comp AS (
  SELECT
    CASE WHEN cmp = 'previous_year' THEN (s - INTERVAL '1 year')::date ELSE s - days END AS cs,
    CASE WHEN cmp = 'previous_year' THEN (e - INTERVAL '1 year')::date ELSE s - 1 END AS ce
  FROM params
)
SELECT (SELECT ce FROM comp) AS date,
  COALESCE(SUM(f.checkouts), 0)::numeric AS value
FROM public_marts.fact_ga4_funnel_daily f
WHERE f.client_slug = {{client_slug}}
  AND f.report_date >= (SELECT cs FROM comp) AND f.report_date <= (SELECT ce FROM comp)
UNION ALL
SELECT (SELECT e FROM params) AS date,
  COALESCE(SUM(f.checkouts), 0)::numeric AS value
FROM public_marts.fact_ga4_funnel_daily f
WHERE f.client_slug = {{client_slug}}
  AND f.report_date >= (SELECT s FROM params) AND f.report_date <= (SELECT e FROM params)
ORDER BY date"""

checkout_id = create_smart_scalar_card("Web Checkouts", CHECKOUT_SQL, TEMPLATE_TAGS)


# ==========================================
# 4. GA4 Web Conversion Rate (smart scalar)
# ==========================================
WEB_CVR_SQL = """WITH params AS (
  SELECT {{report_date_start}}::date AS s, {{report_date_end}}::date AS e,
         ({{report_date_end}}::date - {{report_date_start}}::date + 1) AS days,
         {{compare_mode}} AS cmp
),
comp AS (
  SELECT
    CASE WHEN cmp = 'previous_year' THEN (s - INTERVAL '1 year')::date ELSE s - days END AS cs,
    CASE WHEN cmp = 'previous_year' THEN (e - INTERVAL '1 year')::date ELSE s - 1 END AS ce
  FROM params
)
SELECT (SELECT ce FROM comp) AS date,
  ROUND((SUM(f.purchases) * 100.0 / NULLIF(SUM(f.sessions), 0))::numeric, 2) AS value
FROM public_marts.fact_ga4_funnel_daily f
WHERE f.client_slug = {{client_slug}}
  AND f.report_date >= (SELECT cs FROM comp) AND f.report_date <= (SELECT ce FROM comp)
UNION ALL
SELECT (SELECT e FROM params) AS date,
  ROUND((SUM(f.purchases) * 100.0 / NULLIF(SUM(f.sessions), 0))::numeric, 2) AS value
FROM public_marts.fact_ga4_funnel_daily f
WHERE f.client_slug = {{client_slug}}
  AND f.report_date >= (SELECT s FROM params) AND f.report_date <= (SELECT e FROM params)
ORDER BY date"""

web_cvr_id = create_smart_scalar_card("Web CVR", WEB_CVR_SQL, TEMPLATE_TAGS)


# ==========================================
# 5. GA4 Bounce Rate (smart scalar)
# ==========================================
BOUNCE_SQL = """WITH params AS (
  SELECT {{report_date_start}}::date AS s, {{report_date_end}}::date AS e,
         ({{report_date_end}}::date - {{report_date_start}}::date + 1) AS days,
         {{compare_mode}} AS cmp
),
comp AS (
  SELECT
    CASE WHEN cmp = 'previous_year' THEN (s - INTERVAL '1 year')::date ELSE s - days END AS cs,
    CASE WHEN cmp = 'previous_year' THEN (e - INTERVAL '1 year')::date ELSE s - 1 END AS ce
  FROM params
)
SELECT (SELECT ce FROM comp) AS date,
  ROUND((SUM(f.bounce_rate * f.sessions) / NULLIF(SUM(f.sessions), 0) * 100)::numeric, 1) AS value
FROM public_marts.fact_ga4_funnel_daily f
WHERE f.client_slug = {{client_slug}}
  AND f.report_date >= (SELECT cs FROM comp) AND f.report_date <= (SELECT ce FROM comp)
UNION ALL
SELECT (SELECT e FROM params) AS date,
  ROUND((SUM(f.bounce_rate * f.sessions) / NULLIF(SUM(f.sessions), 0) * 100)::numeric, 1) AS value
FROM public_marts.fact_ga4_funnel_daily f
WHERE f.client_slug = {{client_slug}}
  AND f.report_date >= (SELECT s FROM params) AND f.report_date <= (SELECT e FROM params)
ORDER BY date"""

bounce_id = create_smart_scalar_card("Web Bounce Rate", BOUNCE_SQL, TEMPLATE_TAGS)


# ==========================================
# 6. GA4 Web Funnel (bar chart)
# ==========================================
WEB_FUNNEL_SQL = """SELECT stage, value FROM (
  SELECT 1 AS sort, 'Sessions' AS stage,
    COALESCE(SUM(f.sessions), 0)::numeric AS value
  FROM public_marts.fact_ga4_funnel_daily f
  WHERE f.client_slug = {{client_slug}}
    AND f.report_date >= {{report_date_start}}::date AND f.report_date <= {{report_date_end}}::date
  UNION ALL
  SELECT 2, 'Product Views',
    COALESCE(SUM(f.product_views), 0)::numeric
  FROM public_marts.fact_ga4_funnel_daily f
  WHERE f.client_slug = {{client_slug}}
    AND f.report_date >= {{report_date_start}}::date AND f.report_date <= {{report_date_end}}::date
  UNION ALL
  SELECT 3, 'Add to Cart',
    COALESCE(SUM(f.add_to_carts), 0)::numeric
  FROM public_marts.fact_ga4_funnel_daily f
  WHERE f.client_slug = {{client_slug}}
    AND f.report_date >= {{report_date_start}}::date AND f.report_date <= {{report_date_end}}::date
  UNION ALL
  SELECT 4, 'Checkout',
    COALESCE(SUM(f.checkouts), 0)::numeric
  FROM public_marts.fact_ga4_funnel_daily f
  WHERE f.client_slug = {{client_slug}}
    AND f.report_date >= {{report_date_start}}::date AND f.report_date <= {{report_date_end}}::date
  UNION ALL
  SELECT 5, 'Purchase',
    COALESCE(SUM(f.purchases), 0)::numeric
  FROM public_marts.fact_ga4_funnel_daily f
  WHERE f.client_slug = {{client_slug}}
    AND f.report_date >= {{report_date_start}}::date AND f.report_date <= {{report_date_end}}::date
) sub
ORDER BY sort"""

# Template tags without compare_mode (not needed for funnel)
FUNNEL_TAGS = {
    "report_date_start": TEMPLATE_TAGS["report_date_start"],
    "report_date_end": TEMPLATE_TAGS["report_date_end"],
    "client_slug": TEMPLATE_TAGS["client_slug"]
}

web_funnel_id = create_chart_card(
    "Web Funnel",
    "bar",
    WEB_FUNNEL_SQL,
    FUNNEL_TAGS,
    {
        "graph.dimensions": ["stage"],
        "graph.metrics": ["value"],
        "graph.x_axis.title_text": "",
        "graph.y_axis.title_text": "Count"
    }
)


# ==========================================
# 7. Web Funnel Conversion Rates (table)
# ==========================================
FUNNEL_RATES_SQL = """WITH funnel AS (
  SELECT
    SUM(f.sessions) AS sessions,
    SUM(f.product_views) AS product_views,
    SUM(f.add_to_carts) AS add_to_carts,
    SUM(f.checkouts) AS checkouts,
    SUM(f.purchases) AS purchases
  FROM public_marts.fact_ga4_funnel_daily f
  WHERE f.client_slug = {{client_slug}}
    AND f.report_date >= {{report_date_start}}::date AND f.report_date <= {{report_date_end}}::date
)
SELECT
  sessions AS "Sessions",
  product_views AS "Product Views",
  add_to_carts AS "Add to Carts",
  checkouts AS "Checkouts",
  purchases AS "Purchases",
  ROUND((product_views * 100.0 / NULLIF(sessions, 0))::numeric, 1) || '%' AS "View Rate",
  ROUND((add_to_carts * 100.0 / NULLIF(sessions, 0))::numeric, 2) || '%' AS "ATC Rate",
  ROUND((checkouts * 100.0 / NULLIF(add_to_carts, 0))::numeric, 1) || '%' AS "ATC→Checkout",
  ROUND((purchases * 100.0 / NULLIF(checkouts, 0))::numeric, 1) || '%' AS "Checkout→Purchase",
  ROUND((purchases * 100.0 / NULLIF(sessions, 0))::numeric, 3) || '%' AS "Overall CVR"
FROM funnel"""

funnel_rates_id = create_chart_card(
    "Web Funnel Conversion Rates",
    "table",
    FUNNEL_RATES_SQL,
    FUNNEL_TAGS
)


# ==========================================
# 8. Sessions & Conversion Trend (line chart)
# ==========================================
SESSIONS_TREND_SQL = """SELECT
  f.report_date AS date,
  SUM(f.sessions)::numeric AS sessions,
  SUM(f.add_to_carts)::numeric AS add_to_carts,
  SUM(f.checkouts)::numeric AS checkouts,
  SUM(f.purchases)::numeric AS purchases
FROM public_marts.fact_ga4_funnel_daily f
WHERE f.client_slug = {{client_slug}}
  AND f.report_date >= {{report_date_start}}::date AND f.report_date <= {{report_date_end}}::date
GROUP BY f.report_date
ORDER BY f.report_date"""

sessions_trend_id = create_chart_card(
    "Sessions & Funnel Trend",
    "line",
    SESSIONS_TREND_SQL,
    FUNNEL_TAGS,
    {
        "graph.dimensions": ["date"],
        "graph.metrics": ["sessions", "add_to_carts", "checkouts", "purchases"],
        "graph.y_axis.title_text": "Count",
        "series_settings": {
            "sessions": {"axis": "left"},
            "add_to_carts": {"axis": "right"},
            "checkouts": {"axis": "right"},
            "purchases": {"axis": "right"}
        }
    }
)


# Print summary of created cards
print(f"\n=== Created Cards ===")
print(f"  Web Sessions: {sessions_id}")
print(f"  Web Add to Carts: {atc_id}")
print(f"  Web Checkouts: {checkout_id}")
print(f"  Web CVR: {web_cvr_id}")
print(f"  Web Bounce Rate: {bounce_id}")
print(f"  Web Funnel: {web_funnel_id}")
print(f"  Web Funnel Conversion Rates: {funnel_rates_id}")
print(f"  Sessions & Funnel Trend: {sessions_trend_id}")

# Save card IDs to file for dashboard placement
with open("scripts/ga4_card_ids.json", "w") as f:
    json.dump({
        "sessions": sessions_id,
        "atc": atc_id,
        "checkout": checkout_id,
        "web_cvr": web_cvr_id,
        "bounce_rate": bounce_id,
        "web_funnel": web_funnel_id,
        "funnel_rates": funnel_rates_id,
        "sessions_trend": sessions_trend_id
    }, f, indent=2)
print("\n[OK] Card IDs saved to scripts/ga4_card_ids.json")
