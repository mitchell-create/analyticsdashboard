-- Email & Klaviyo: Opens and clicks by day (Line chart)
SELECT
  report_date AS date,
  COALESCE(SUM(opens), 0) AS opens,
  COALESCE(SUM(clicks), 0) AS clicks
FROM public_marts.fact_klaviyo_daily
WHERE client_slug = {{client}}
GROUP BY report_date
ORDER BY report_date
