-- Email & Klaviyo: Top Flows by Revenue (Table)
SELECT
  flow_id,
  MAX(report_date) AS latest_date,
  COALESCE(SUM(sent), 0) AS sent,
  COALESCE(SUM(opens), 0) AS opens,
  COALESCE(SUM(clicks), 0) AS clicks,
  COALESCE(SUM(conversions), 0) AS conversions,
  COALESCE(SUM(revenue), 0) AS revenue,
  CASE WHEN SUM(sent) > 0
    THEN ROUND(SUM(opens)::numeric / SUM(sent) * 100, 1) ELSE 0 END AS open_rate_pct,
  CASE WHEN SUM(sent) > 0
    THEN ROUND(SUM(clicks)::numeric / SUM(sent) * 100, 1) ELSE 0 END AS click_rate_pct
FROM public_marts.fact_klaviyo_daily
WHERE client_slug = {{client}}
  AND record_type = 'flow'
  AND flow_id IS NOT NULL
GROUP BY flow_id
ORDER BY revenue DESC
LIMIT 25
