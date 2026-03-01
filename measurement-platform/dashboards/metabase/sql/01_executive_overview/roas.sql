-- Executive Overview: ROAS (revenue / spend) (Table or Number)
SELECT
  (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily) AS revenue,
  (SELECT COALESCE(SUM(spend), 0) FROM public_marts.fact_spend_daily) AS spend,
  CASE WHEN (SELECT COALESCE(SUM(spend), 0) FROM public_marts.fact_spend_daily) = 0 THEN 0
       ELSE (SELECT COALESCE(SUM(revenue), 0) FROM public_marts.fact_kpi_daily)
            / NULLIF((SELECT SUM(spend) FROM public_marts.fact_spend_daily), 0) END AS roas
