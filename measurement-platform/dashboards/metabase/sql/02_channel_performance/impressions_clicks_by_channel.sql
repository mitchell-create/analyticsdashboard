-- Channel Performance: Impressions and clicks by channel (Line chart)
SELECT report_date AS date, channel, SUM(impressions) AS impressions, SUM(clicks) AS clicks
FROM public_marts.fact_spend_daily
GROUP BY report_date, channel
ORDER BY report_date, channel
