-- Email & Klaviyo: Total Attributed Revenue (Scalar / Big Number)
-- Filtered by client_slug via {{client}} variable
SELECT COALESCE(SUM(revenue), 0) AS total_revenue
FROM public_marts.fact_klaviyo_daily
WHERE client_slug = {{client}}
