-- KPI Number Card: ROAS (Revenue / Spend) with previous-period comparison
-- Display: smartscalar (Trend) — Metabase shows latest value as big number
-- with ↑/↓ arrow and % change vs the previous row.
--
-- Returns exactly 2 rows:
--   Row 1: previous period aggregate (same number of days before start_date)
--   Row 2: current period aggregate (start_date to end_date)
--
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
      (SELECT SUM(spend) FROM public_marts.fact_spend_daily
       WHERE report_date >= (SELECT range_start - period_days FROM params)
         AND report_date <  (SELECT range_start FROM params)), 0),
    0)::numeric, 2) AS roas

UNION ALL

SELECT
  (SELECT range_end FROM params) AS date,
  ROUND(COALESCE(
    (SELECT SUM(revenue) FROM public_marts.fact_kpi_daily
     WHERE report_date >= (SELECT range_start FROM params)
       AND report_date <= (SELECT range_end FROM params))
    / NULLIF(
      (SELECT SUM(spend) FROM public_marts.fact_spend_daily
       WHERE report_date >= (SELECT range_start FROM params)
         AND report_date <= (SELECT range_end FROM params)), 0),
    0)::numeric, 2) AS roas

ORDER BY date
