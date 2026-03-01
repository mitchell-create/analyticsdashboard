-- Email & Klaviyo: Campaigns summary (Table)
SELECT campaign_id, report_date, sent, opens, clicks
FROM public_marts.fact_klaviyo_daily
ORDER BY report_date DESC, campaign_id
LIMIT 50
