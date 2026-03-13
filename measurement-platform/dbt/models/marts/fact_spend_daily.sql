-- fact_spend_daily — Daily spend by channel (union of Meta, Google, TikTok staging)
{{
  config(
    materialized='table',
    schema='marts'
  )
}}

with meta as (
  select report_date, channel, spend, impressions, clicks from {{ ref('stg_meta_spend') }}
),
google as (
  select report_date, channel, spend, impressions, clicks from {{ ref('stg_google_spend') }}
),
tiktok as (
  select report_date, channel, spend, impressions, clicks from {{ ref('stg_tiktok_spend') }}
),
unioned as (
  select * from meta
  union all
  select * from google
  union all
  select * from tiktok
)
select
  'expand' as client_slug,
  report_date,
  channel,
  coalesce(sum(spend), 0) as spend,
  sum(impressions) as impressions,
  sum(clicks) as clicks
from unioned
group by 1, 2, 3
