-- GMV Max summary KPIs (Chellegum only)
SELECT
  SUM(gross_revenue) AS total_revenue,
  SUM(cost) AS total_cost,
  SUM(orders) AS total_orders,
  CASE WHEN SUM(cost) > 0 THEN SUM(gross_revenue) / SUM(cost) ELSE 0 END AS overall_roas,
  CASE WHEN SUM(orders) > 0 THEN SUM(cost) / SUM(orders) ELSE 0 END AS avg_cost_per_order,
  MIN(report_date) AS first_date,
  MAX(report_date) AS last_date
FROM public_marts.fact_tiktok_gmv_max_daily
WHERE client_slug = 'chubble'
