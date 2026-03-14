-- GMV Max orders by day (Chellegum only)
SELECT
  report_date AS date,
  orders,
  active_campaigns
FROM public_marts.fact_tiktok_gmv_max_daily
WHERE client_slug = 'chubble'
ORDER BY report_date
