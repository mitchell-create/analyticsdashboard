-- Executive Overview: Daily revenue (Line chart)
SELECT report_date AS date, COALESCE(SUM(revenue), 0) AS revenue
FROM public_marts.fact_kpi_daily
GROUP BY report_date
ORDER BY report_date
