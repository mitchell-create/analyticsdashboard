-- Email & Klaviyo: Engagement Rates over time (Line chart)
-- Open rate, click rate, click-to-open rate, conversion rate
SELECT
  report_date AS date,
  ROUND(AVG(open_rate) * 100, 1) AS avg_open_rate_pct,
  ROUND(AVG(click_rate) * 100, 1) AS avg_click_rate_pct,
  ROUND(AVG(click_to_open_rate) * 100, 1) AS avg_click_to_open_pct,
  ROUND(AVG(conversion_rate) * 100, 1) AS avg_conversion_rate_pct
FROM public_marts.fact_klaviyo_daily
WHERE client_slug = {{client}}
  AND record_type = 'campaign'
  AND sent > 0
GROUP BY report_date
ORDER BY report_date
