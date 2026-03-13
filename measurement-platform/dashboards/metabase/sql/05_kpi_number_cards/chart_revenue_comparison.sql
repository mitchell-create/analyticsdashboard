-- Comparison Line Chart: Daily Revenue — Current vs Previous Period
-- Both periods are aligned on the same date axis (previous dates shifted forward).
-- Display: line chart with series split by "period" column.
-- Filters: report_date_start, report_date_end

WITH params AS (
  SELECT
    {{report_date_start}}::date AS range_start,
    {{report_date_end}}::date   AS range_end,
    ({{report_date_end}}::date - {{report_date_start}}::date + 1) AS period_days
)
SELECT
  'Current Period' AS period,
  report_date AS date,
  COALESCE(SUM(revenue), 0) AS revenue
FROM public_marts.fact_kpi_daily
WHERE report_date >= (SELECT range_start FROM params)
  AND report_date <= (SELECT range_end FROM params)
GROUP BY report_date

UNION ALL

SELECT
  'Previous Period' AS period,
  (report_date + (SELECT period_days FROM params))::date AS date,
  COALESCE(SUM(revenue), 0) AS revenue
FROM public_marts.fact_kpi_daily
WHERE report_date >= (SELECT range_start - period_days FROM params)
  AND report_date <  (SELECT range_start FROM params)
GROUP BY report_date, (SELECT period_days FROM params)

ORDER BY date, period
