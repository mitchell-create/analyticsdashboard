-- KPI Number Card: AOV (Average Order Value) with previous-period comparison
-- AOV = Total Revenue / Total Orders
-- Display: smartscalar (Trend)
-- Filters: report_date_start, report_date_end

WITH params AS (
  SELECT
    {{report_date_start}}::date AS range_start,
    {{report_date_end}}::date   AS range_end,
    ({{report_date_end}}::date - {{report_date_start}}::date + 1) AS period_days
)
SELECT
  (SELECT range_start - 1 FROM params) AS date,
  ROUND(COALESCE(
    (SELECT SUM(revenue) FROM public_marts.fact_kpi_daily
     WHERE report_date >= (SELECT range_start - period_days FROM params)
       AND report_date <  (SELECT range_start FROM params))
    / NULLIF(
      (SELECT SUM(orders) FROM public_marts.fact_kpi_daily
       WHERE report_date >= (SELECT range_start - period_days FROM params)
         AND report_date <  (SELECT range_start FROM params)), 0),
    0)::numeric, 2) AS aov

UNION ALL

SELECT
  (SELECT range_end FROM params) AS date,
  ROUND(COALESCE(
    (SELECT SUM(revenue) FROM public_marts.fact_kpi_daily
     WHERE report_date >= (SELECT range_start FROM params)
       AND report_date <= (SELECT range_end FROM params))
    / NULLIF(
      (SELECT SUM(orders) FROM public_marts.fact_kpi_daily
       WHERE report_date >= (SELECT range_start FROM params)
         AND report_date <= (SELECT range_end FROM params)), 0),
    0)::numeric, 2) AS aov

ORDER BY date
