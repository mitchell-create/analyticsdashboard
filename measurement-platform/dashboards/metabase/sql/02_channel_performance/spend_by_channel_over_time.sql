-- Channel Performance: Spend by channel over time (Line chart)
SELECT report_date AS date, channel, COALESCE(SUM(spend), 0) AS spend
FROM public_marts.fact_spend_daily
GROUP BY report_date, channel
ORDER BY report_date, channel
