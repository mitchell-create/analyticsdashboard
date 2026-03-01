-- Channel Performance: ROAS by channel (Table)
SELECT s.channel,
  COALESCE(SUM(s.spend), 0) AS spend,
  (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily) AS revenue,
  CASE WHEN SUM(s.spend) = 0 THEN 0
       ELSE (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily) / NULLIF(SUM(s.spend), 0) END AS roas
FROM public_marts.fact_spend_daily s
GROUP BY s.channel
ORDER BY spend DESC
