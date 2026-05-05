-- Email & Klaviyo: Revenue Over Time — campaign + flow revenue by date (Line chart)
SELECT
  report_date AS date,
  SUM(CASE WHEN record_type = 'campaign' THEN revenue ELSE 0 END) AS campaign_revenue,
  SUM(CASE WHEN record_type = 'flow' THEN revenue ELSE 0 END) AS flow_revenue,
  COALESCE(SUM(revenue), 0) AS total_revenue
FROM public_marts.fact_klaviyo_daily
WHERE client_slug = {{client}}
GROUP BY report_date
ORDER BY report_date
