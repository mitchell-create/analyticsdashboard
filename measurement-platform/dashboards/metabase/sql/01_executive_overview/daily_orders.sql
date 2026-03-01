-- Executive Overview: Daily orders (Line chart)
SELECT report_date AS date, COALESCE(SUM(orders), 0) AS orders
FROM public_marts.fact_kpi_daily
GROUP BY report_date
ORDER BY report_date
