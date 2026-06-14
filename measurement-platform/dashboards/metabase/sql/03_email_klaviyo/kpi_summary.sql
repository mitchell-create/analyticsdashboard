-- Email & Klaviyo: KPI Summary Cards (scalar values for big-number cards)
SELECT
  COALESCE(SUM(sent), 0) AS total_sent,
  COALESCE(SUM(opens), 0) AS total_opens,
  COALESCE(SUM(clicks), 0) AS total_clicks,
  COALESCE(SUM(conversions), 0) AS total_conversions,
  COALESCE(SUM(revenue), 0) AS total_revenue,
  COALESCE(SUM(unsubscribes), 0) AS total_unsubscribes,
  COALESCE(SUM(bounced), 0) AS total_bounced,
  COALESCE(SUM(spam_complaints), 0) AS total_spam_complaints,
  CASE WHEN SUM(sent) > 0
    THEN ROUND(SUM(opens)::numeric / SUM(sent) * 100, 1) ELSE 0 END AS overall_open_rate_pct,
  CASE WHEN SUM(sent) > 0
    THEN ROUND(SUM(clicks)::numeric / SUM(sent) * 100, 1) ELSE 0 END AS overall_click_rate_pct,
  CASE WHEN SUM(sent) > 0
    THEN ROUND(SUM(conversions)::numeric / SUM(sent) * 100, 1) ELSE 0 END AS overall_conversion_rate_pct,
  CASE WHEN SUM(sent) > 0
    THEN ROUND(SUM(unsubscribes)::numeric / SUM(sent) * 100, 1) ELSE 0 END AS overall_unsubscribe_rate_pct
FROM public_marts.fact_klaviyo_daily
WHERE client_slug = {{client}}
