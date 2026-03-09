-- fact_spend_daily — Daily spend by channel (union of Meta, Google, TikTok staging)
{{
  config(
    materialized='incremental',
    schema='marts',
    unique_key=['client_slug', 'report_date', 'channel'],
    incremental_strategy='merge',
    on_schema_change='sync_all_columns'
  )
}}

with meta as (
  select client_slug, report_date, channel, spend, impressions, clicks from {{ ref('stg_meta_spend') }}
),
google as (
  select client_slug, report_date, channel, spend, impressions, clicks from {{ ref('stg_google_spend') }}
),
tiktok as (
  select client_slug, report_date, channel, spend, impressions, clicks from {{ ref('stg_tiktok_spend') }}
),
unioned as (
  select * from meta
  union all
  select * from google
  union all
  select * from tiktok
)
select
  client_slug,
  report_date,
  channel,
  coalesce(sum(spend), 0) as spend,
  sum(impressions) as impressions,
  sum(clicks) as clicks
from unioned
group by 1, 2, 3
