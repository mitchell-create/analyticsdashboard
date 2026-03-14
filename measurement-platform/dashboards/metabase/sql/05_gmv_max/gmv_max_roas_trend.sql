-- GMV Max ROAS trend (Chellegum only)
SELECT
  report_date AS date,
  roas,
  cost_per_order
FROM public_marts.fact_tiktok_gmv_max_daily
WHERE client_slug = 'chubble'
ORDER BY report_date
