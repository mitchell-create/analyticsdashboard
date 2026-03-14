-- GMV Max revenue vs cost over time (Chellegum only)
SELECT
  report_date AS date,
  gross_revenue,
  cost
FROM public_marts.fact_tiktok_gmv_max_daily
WHERE client_slug = 'chubble'
ORDER BY report_date
