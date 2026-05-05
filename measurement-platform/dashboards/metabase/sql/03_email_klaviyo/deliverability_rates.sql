-- Email & Klaviyo: Deliverability Rates over time (Line chart)
-- Only campaigns have pre-computed rates; flows computed from counts
SELECT
  report_date AS date,
  ROUND(AVG(delivery_rate) * 100, 1) AS avg_delivery_rate_pct,
  ROUND(AVG(bounce_rate) * 100, 1) AS avg_bounce_rate_pct,
  ROUND(AVG(unsubscribe_rate) * 100, 1) AS avg_unsubscribe_rate_pct
FROM public_marts.fact_klaviyo_daily
WHERE client_slug = {{client}}
  AND record_type = 'campaign'
  AND sent > 0
GROUP BY report_date
ORDER BY report_date
