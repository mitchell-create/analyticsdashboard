-- Run these in Supabase SQL Editor to diagnose why fact_kpi_geo_daily shows zeros for Texas
-- Copy and run each query one at a time.

-- 1. Check raw orders: do we have shipping_address and province_code?
SELECT 
  COUNT(*) as total_orders,
  COUNT(shipping_address) as with_shipping_address,
  COUNT(CASE WHEN shipping_address->>'province_code' IS NOT NULL AND shipping_address->>'province_code' != '' THEN 1 END) as with_province_code,
  COUNT(CASE WHEN shipping_address->>'country_code' = 'US' THEN 1 END) as us_orders
FROM raw.orders
WHERE financial_status IN ('paid', 'partially_paid');

-- 2. Sample of province codes in raw data (top 10)
SELECT 
  shipping_address->>'province_code' as province_code,
  shipping_address->>'country_code' as country_code,
  COUNT(*) as cnt
FROM raw.orders
WHERE financial_status IN ('paid', 'partially_paid')
  AND shipping_address IS NOT NULL
GROUP BY 1, 2
ORDER BY cnt DESC
LIMIT 10;

-- 3. Does stg_shopify_orders_geo have any rows?
SELECT * FROM public_staging.stg_shopify_orders_geo ORDER BY report_date DESC LIMIT 20;

-- 4. Date range of orders in fact_kpi_daily (where dates come from)
SELECT MIN(report_date) as min_date, MAX(report_date) as max_date, COUNT(*) as days
FROM public_marts.fact_kpi_daily;
