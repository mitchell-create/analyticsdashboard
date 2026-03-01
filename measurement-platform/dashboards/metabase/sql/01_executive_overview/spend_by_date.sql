-- Executive Overview: Spend by date (Line chart)
SELECT report_date AS date, COALESCE(SUM(spend), 0) AS spend
FROM public_marts.fact_spend_daily
GROUP BY report_date
ORDER BY report_date
