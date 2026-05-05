-- Email & Klaviyo: Revenue by Record Type — campaigns vs flows (Pie / Bar)
SELECT
  record_type,
  COALESCE(SUM(revenue), 0) AS revenue
FROM public_marts.fact_klaviyo_daily
WHERE client_slug = {{client}}
GROUP BY record_type
ORDER BY revenue DESC
