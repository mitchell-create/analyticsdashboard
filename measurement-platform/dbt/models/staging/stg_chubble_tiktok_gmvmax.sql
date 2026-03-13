-- stg_chubble_tiktok_gmvmax — Staging for Chubble's TikTok GMV Max campaigns (from Coupler.io)
-- Aggregates campaign-level rows to daily totals to match fact_spend_daily grain.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('coupler_chubble', 'tiktok_gmv_max') }}
),

daily as (
  select
    (stat_time_day::date) as report_date,
    'tiktok' as channel,
    coalesce(sum(cost::numeric(14, 2)), 0) as spend,
    -- GMV Max doesn't expose impressions/clicks; null for now
    null::bigint as impressions,
    null::bigint as clicks,
    -- Extra GMV Max metrics (useful for ROAS / CPA analysis)
    coalesce(sum(orders::bigint), 0) as tiktok_orders,
    coalesce(sum(gross_revenue::numeric(14, 2)), 0) as tiktok_revenue
  from source
  where cost > 0 or orders::bigint > 0
  group by 1
)

select * from daily
