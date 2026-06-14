-- Email & Klaviyo: Unsubscribes & Spam Complaints over time (Line chart)
SELECT
  report_date AS date,
  COALESCE(SUM(unsubscribes), 0) AS unsubscribes,
  COALESCE(SUM(spam_complaints), 0) AS spam_complaints,
  COALESCE(SUM(bounced), 0) AS bounced
FROM public_marts.fact_klaviyo_daily
WHERE client_slug = {{client}}
GROUP BY report_date
ORDER BY report_date
