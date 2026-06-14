-- Email & Klaviyo: Email sends by day (Line chart)
SELECT report_date AS date, COALESCE(SUM(sent), 0) AS sent
FROM public_marts.fact_klaviyo_daily
WHERE client_slug = {{client}}
GROUP BY report_date
ORDER BY report_date
