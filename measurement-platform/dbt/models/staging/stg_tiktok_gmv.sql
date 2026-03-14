-- stg_tiktok_gmv — Staging for TikTok GMV Max daily report (from Coupler.io)
-- Adjust column names below to match Coupler's TikTok connector output.
-- Common TikTok GMV API columns: stat_time_day, total_purchase_value, total_purchase, cost.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('coupler_chubble', 'tiktok_gmv_max') }}
),

renamed as (
  select
    date_trunc('day', (stat_time_day::date))::date as report_date,
    coalesce((total_purchase_value)::numeric(14, 2), 0) as gmv,
    coalesce((total_purchase)::int, 0) as orders,
    coalesce((cost)::numeric(14, 2), 0) as spend
  from source
)

select * from renamed
