-- GMV Max daily performance (Chellegum only)
SELECT
  report_date AS date,
  gross_revenue,
  cost,
  orders,
  roas
FROM public_marts.fact_tiktok_gmv_max_daily
WHERE client_slug = 'chubble'
ORDER BY report_date
