-- fact_spend_daily_fx — Spend with currency conversion (ad platform → Shopify currency)
-- Joins fact_spend_daily with currency_config to normalize spend to Shopify's base currency.
-- For clients where ad platforms bill in a different currency (e.g. CAD) than Shopify (e.g. USD),
-- this view multiplies spend by ad_to_shopify_rate. Falls back to rate=1 when no config exists.
{{
  config(
    materialized='view',
    schema='marts'
  )
}}

select
  s.client_slug,
  s.report_date,
  s.channel,
  s.spend * coalesce(c.ad_to_shopify_rate, 1) as spend,
  s.impressions,
  s.clicks
from {{ ref('fact_spend_daily') }} s
left join {{ source('marts_config', 'currency_config') }} c
  on s.client_slug = c.client_slug
