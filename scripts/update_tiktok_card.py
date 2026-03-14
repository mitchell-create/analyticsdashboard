"""Update TikTok Frequency card 460 to use period-level API data."""
import requests
import json

MB_URL = "http://localhost:3000"
MB_KEY = "mb_shG81kdEkgdKIR7njalW+w2SIvEk8sAygAPT6vIyze0="
HEADERS = {"x-api-key": MB_KEY, "Content-Type": "application/json"}

# Card 460: TikTok Frequency - use period-level API with daily fallback
TIKTOK_FREQ_SQL = """WITH params AS (
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
tiktok_accounts AS (
  SELECT account_id FROM public_marts.client_ad_accounts
  WHERE client_slug = {{client_slug}} AND platform = 'tiktok'
)
SELECT (SELECT ce FROM comp) AS date,
  ROUND(COALESCE(
    (SELECT m.frequency
     FROM tiktok_accounts a
     CROSS JOIN LATERAL raw.get_tiktok_period_metrics(a.account_id, (SELECT cs FROM comp), (SELECT ce FROM comp)) m
     LIMIT 1),
    (SELECT SUM((r.metrics->>'impressions')::numeric) / NULLIF(SUM((r.metrics->>'reach')::numeric), 0)
     FROM raw.tiktok_advertisers_reports_daily r
     WHERE r.advertiser_id IN (SELECT account_id::bigint FROM tiktok_accounts)
       AND r.stat_time_day::date >= (SELECT cs FROM comp) AND r.stat_time_day::date <= (SELECT ce FROM comp)
       AND (r.metrics->>'spend')::numeric > 0)
  )::numeric, 2) AS value
UNION ALL
SELECT (SELECT e FROM params) AS date,
  ROUND(COALESCE(
    (SELECT m.frequency
     FROM tiktok_accounts a
     CROSS JOIN LATERAL raw.get_tiktok_period_metrics(a.account_id, (SELECT s FROM params), (SELECT e FROM params)) m
     LIMIT 1),
    (SELECT SUM((r.metrics->>'impressions')::numeric) / NULLIF(SUM((r.metrics->>'reach')::numeric), 0)
     FROM raw.tiktok_advertisers_reports_daily r
     WHERE r.advertiser_id IN (SELECT account_id::bigint FROM tiktok_accounts)
       AND r.stat_time_day::date >= (SELECT s FROM params) AND r.stat_time_day::date <= (SELECT e FROM params)
       AND (r.metrics->>'spend')::numeric > 0)
  )::numeric, 2) AS value
ORDER BY date"""

# Get current card and update
r = requests.get(f"{MB_URL}/api/card/460", headers=HEADERS)
r.raise_for_status()
card = r.json()

dq = card["dataset_query"]
if "stages" in dq:
    dq["stages"][0]["native"] = TIKTOK_FREQ_SQL
elif "native" in dq:
    dq["native"]["query"] = TIKTOK_FREQ_SQL

r = requests.put(f"{MB_URL}/api/card/460",
                 headers=HEADERS,
                 json={"dataset_query": dq})
r.raise_for_status()
print("[OK] Card 460 (TikTok Frequency) updated to use period-level API")
