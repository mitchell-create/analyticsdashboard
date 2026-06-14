-- Email & Klaviyo: Campaigns summary (Table)
SELECT
  campaign_id,
  report_date,
  sent,
  opens,
  clicks,
  conversions,
  revenue,
  CASE WHEN sent > 0 THEN ROUND(opens::numeric / sent * 100, 1) ELSE 0 END AS open_rate_pct,
  CASE WHEN sent > 0 THEN ROUND(clicks::numeric / sent * 100, 1) ELSE 0 END AS click_rate_pct,
  unsubscribes,
  bounced
FROM public_marts.fact_klaviyo_daily
WHERE client_slug = {{client}}
  AND record_type = 'campaign'
ORDER BY report_date DESC, campaign_id
LIMIT 50
