"""Update Metabase cards 335 (Frequency), 337 (CVR) to use period-level Meta API data."""
import requests
import json

MB_URL = "http://localhost:3000"
MB_KEY = "mb_shG81kdEkgdKIR7njalW+w2SIvEk8sAygAPT6vIyze0="
HEADERS = {"x-api-key": MB_KEY, "Content-Type": "application/json"}


def update_card(card_id, new_sql, card_name):
    """Update a Metabase card's native SQL query."""
    # Get current card
    r = requests.get(f"{MB_URL}/api/card/{card_id}", headers=HEADERS)
    r.raise_for_status()
    card = r.json()

    # Update the native query
    dq = card["dataset_query"]
    if "stages" in dq:
        dq["stages"][0]["native"] = new_sql
    elif "native" in dq:
        dq["native"]["query"] = new_sql

    r = requests.put(f"{MB_URL}/api/card/{card_id}",
                     headers=HEADERS,
                     json={"dataset_query": dq})
    r.raise_for_status()
    print(f"[OK] Card {card_id} ({card_name}) updated")


# ==========================================
# Card 335: Meta Frequency
# ==========================================
FREQ_SQL = """WITH params AS (
  SELECT {{report_date_start}}::date AS s, {{report_date_end}}::date AS e,
         ({{report_date_end}}::date - {{report_date_start}}::date + 1) AS days,
         {{compare_mode}} AS cmp
),
comp AS (
  SELECT
    CASE WHEN cmp = 'previous_year' THEN (s - INTERVAL '1 year')::date ELSE s - days END AS cs,
    CASE WHEN cmp = 'previous_year' THEN (e - INTERVAL '1 year')::date ELSE s - 1 END AS ce
  FROM params
),
accounts AS (
  SELECT account_id FROM public_marts.client_ad_accounts
  WHERE client_slug = {{client_slug}} AND platform = 'meta'
)
SELECT (SELECT ce FROM comp) AS date,
  ROUND(COALESCE(
    (SELECT m.frequency
     FROM accounts a
     CROSS JOIN LATERAL raw.get_meta_period_ctr(a.account_id, (SELECT cs FROM comp), (SELECT ce FROM comp)) m
     LIMIT 1),
    (SELECT SUM(d.impressions::numeric) / NULLIF(SUM(d.reach::numeric), 0)
     FROM raw.meta_customaccount_insights_daily d
     JOIN accounts a ON d.account_id = a.account_id
     WHERE d.date_start >= (SELECT cs FROM comp) AND d.date_start <= (SELECT ce FROM comp))
  )::numeric, 2) AS value
UNION ALL
SELECT (SELECT e FROM params) AS date,
  ROUND(COALESCE(
    (SELECT m.frequency
     FROM accounts a
     CROSS JOIN LATERAL raw.get_meta_period_ctr(a.account_id, (SELECT s FROM params), (SELECT e FROM params)) m
     LIMIT 1),
    (SELECT SUM(d.impressions::numeric) / NULLIF(SUM(d.reach::numeric), 0)
     FROM raw.meta_customaccount_insights_daily d
     JOIN accounts a ON d.account_id = a.account_id
     WHERE d.date_start >= (SELECT s FROM params) AND d.date_start <= (SELECT e FROM params))
  )::numeric, 2) AS value
ORDER BY date"""

update_card(335, FREQ_SQL, "Meta Frequency")


# ==========================================
# Card 337: Meta CVR
# ==========================================
CVR_SQL = """WITH params AS (
  SELECT {{report_date_start}}::date AS s, {{report_date_end}}::date AS e,
         ({{report_date_end}}::date - {{report_date_start}}::date + 1) AS days,
         {{compare_mode}} AS cmp
),
comp AS (
  SELECT
    CASE WHEN cmp = 'previous_year' THEN (s - INTERVAL '1 year')::date ELSE s - days END AS cs,
    CASE WHEN cmp = 'previous_year' THEN (e - INTERVAL '1 year')::date ELSE s - 1 END AS ce
  FROM params
),
accounts AS (
  SELECT account_id FROM public_marts.client_ad_accounts
  WHERE client_slug = {{client_slug}} AND platform = 'meta'
)
SELECT (SELECT ce FROM comp) AS date,
  ROUND(COALESCE(
    (SELECT m.omni_purchase_count * 100.0 / NULLIF(m.clicks, 0)
     FROM accounts a
     CROSS JOIN LATERAL raw.get_meta_period_ctr(a.account_id, (SELECT cs FROM comp), (SELECT ce FROM comp)) m
     LIMIT 1),
    (SELECT SUM((SELECT COALESCE(SUM((e->>'value')::numeric),0)
                 FROM jsonb_array_elements(d.actions) e
                 WHERE e->>'action_type'='omni_purchase'))
            * 100.0 / NULLIF(SUM(d.clicks::numeric), 0)
     FROM raw.meta_customaccount_insights_daily d
     JOIN accounts a ON d.account_id = a.account_id
     WHERE d.date_start >= (SELECT cs FROM comp) AND d.date_start <= (SELECT ce FROM comp))
  )::numeric, 2) AS value
UNION ALL
SELECT (SELECT e FROM params) AS date,
  ROUND(COALESCE(
    (SELECT m.omni_purchase_count * 100.0 / NULLIF(m.clicks, 0)
     FROM accounts a
     CROSS JOIN LATERAL raw.get_meta_period_ctr(a.account_id, (SELECT s FROM params), (SELECT e FROM params)) m
     LIMIT 1),
    (SELECT SUM((SELECT COALESCE(SUM((e->>'value')::numeric),0)
                 FROM jsonb_array_elements(d.actions) e
                 WHERE e->>'action_type'='omni_purchase'))
            * 100.0 / NULLIF(SUM(d.clicks::numeric), 0)
     FROM raw.meta_customaccount_insights_daily d
     JOIN accounts a ON d.account_id = a.account_id
     WHERE d.date_start >= (SELECT s FROM params) AND d.date_start <= (SELECT e FROM params))
  )::numeric, 2) AS value
ORDER BY date"""

update_card(337, CVR_SQL, "Meta CVR")

print("\n[OK] All cards updated!")
