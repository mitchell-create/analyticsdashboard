"""
Update Google Frequency → Google Purchases, and investigate TikTok frequency.
"""
import requests
import json

MB_URL = "http://localhost:3000"
MB_KEY = "mb_shG81kdEkgdKIR7njalW+w2SIvEk8sAygAPT6vIyze0="
HEADERS = {"x-api-key": MB_KEY, "Content-Type": "application/json"}


def update_card_sql_and_name(card_id, new_sql, new_name=None):
    """Update a Metabase card's SQL and optionally its name."""
    r = requests.get(f"{MB_URL}/api/card/{card_id}", headers=HEADERS)
    r.raise_for_status()
    card = r.json()

    dq = card["dataset_query"]
    if "stages" in dq:
        dq["stages"][0]["native"] = new_sql
    elif "native" in dq:
        dq["native"]["query"] = new_sql

    update_payload = {"dataset_query": dq}
    if new_name:
        update_payload["name"] = new_name

    r = requests.put(f"{MB_URL}/api/card/{card_id}",
                     headers=HEADERS,
                     json=update_payload)
    r.raise_for_status()
    print(f"[OK] Card {card_id} updated -> {new_name or card.get('name')}")


# ==========================================
# Card 350: Google Frequency → Google Purchases
# ==========================================
PURCHASES_SQL = """WITH params AS (
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
  COALESCE(SUM(g.metrics_conversions), 0)::numeric AS value
FROM raw.google_campaign g
JOIN public_marts.client_ad_accounts a ON split_part(g.campaign_resource_name, '/', 2) = a.account_id AND a.platform = 'google'
WHERE a.client_slug = {{client_slug}}
  AND g.segments_date::date >= (SELECT cs FROM comp) AND g.segments_date::date <= (SELECT ce FROM comp)
UNION ALL
SELECT (SELECT e FROM params) AS date,
  COALESCE(SUM(g.metrics_conversions), 0)::numeric AS value
FROM raw.google_campaign g
JOIN public_marts.client_ad_accounts a ON split_part(g.campaign_resource_name, '/', 2) = a.account_id AND a.platform = 'google'
WHERE a.client_slug = {{client_slug}}
  AND g.segments_date::date >= (SELECT s FROM params) AND g.segments_date::date <= (SELECT e FROM params)
ORDER BY date"""

update_card_sql_and_name(350, PURCHASES_SQL, "Google Purchases")


# ==========================================
# Find TikTok frequency card
# ==========================================
# Check Dashboard 162 for TikTok cards
r = requests.get(f"{MB_URL}/api/dashboard/162", headers=HEADERS)
r.raise_for_status()
dash = r.json()
cards = dash.get("dashcards", dash.get("ordered_cards", []))
print("\n=== TikTok cards on Dashboard 162 ===")
for c in cards:
    card = c.get("card", {})
    card_id = card.get("id", c.get("card_id", "?"))
    name = card.get("name", "?")
    if card_id and "tiktok" in str(name).lower():
        print(f"  Card {card_id}: {name}")

# Also check Dashboard 131
r = requests.get(f"{MB_URL}/api/dashboard/131", headers=HEADERS)
r.raise_for_status()
dash = r.json()
cards = dash.get("dashcards", dash.get("ordered_cards", []))
print("\n=== TikTok cards on Dashboard 131 ===")
for c in cards:
    card = c.get("card", {})
    card_id = card.get("id", c.get("card_id", "?"))
    name = card.get("name", "?")
    if card_id and ("tiktok" in str(name).lower() or "TikTok" in str(name)):
        print(f"  Card {card_id}: {name}")

print("\n[OK] Done!")
