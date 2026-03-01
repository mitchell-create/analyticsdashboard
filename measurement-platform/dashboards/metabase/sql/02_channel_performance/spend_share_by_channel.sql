-- Channel Performance: Spend share by channel (Pie chart)
SELECT channel, COALESCE(SUM(spend), 0) AS spend
FROM public_marts.fact_spend_daily
GROUP BY channel
ORDER BY spend DESC
