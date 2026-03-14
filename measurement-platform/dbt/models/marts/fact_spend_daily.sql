-- fact_spend_daily — Daily spend + purchase value by channel (union of Meta, Google, TikTok staging)
{{
  config(
    materialized='table',
    schema='marts'
  )
}}

with meta as (
  select report_date, channel, spend, impressions, clicks, purchase_value from {{ ref('stg_meta_spend') }}
),
google as (
  select report_date, channel, spend, impressions, clicks, 0::numeric(14, 2) as purchase_value from {{ ref('stg_google_spend') }}
),
tiktok as (
  select report_date, channel, spend, impressions, clicks, purchase_value from {{ ref('stg_tiktok_spend') }}
),
unioned as (
  select * from meta
  union all
  select * from google
  union all
  select * from tiktok
)
select
  report_date,
  channel,
  coalesce(sum(spend), 0) as spend,
  sum(impressions) as impressions,
  sum(clicks) as clicks,
  coalesce(sum(purchase_value), 0) as purchase_value,
  case when sum(spend) > 0 then sum(purchase_value) / sum(spend) else 0 end as roas
from unioned
group by 1, 2
