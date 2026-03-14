-- stg_tiktok_spend — Staging for TikTok Ads (web) daily spend + purchase value (from Airbyte raw)
-- Extracts spend, impressions, clicks, and purchase_value from tiktok_advertisers_reports_daily.
-- TikTok web ads purchase_value comes from metrics JSON (complete_payment_roas * spend or total_complete_payment_value).

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_airbyte', 'tiktok_advertisers_reports_daily') }}
),

renamed as (
  select
    date_trunc('day', (stat_time_day::date))::date as report_date,
    'tiktok' as channel,
    coalesce((metrics->>'spend')::numeric(14, 2), 0) as spend,
    (metrics->>'impressions')::bigint as impressions,
    (metrics->>'clicks')::bigint as clicks,
    -- Extract purchase value from TikTok metrics JSON
    -- Try total_complete_payment_value first, fall back to value_per_complete_payment * complete_payment
    coalesce(
      (metrics->>'total_complete_payment_value')::numeric(14, 2),
      (metrics->>'complete_payment_value')::numeric(14, 2),
      0
    )::numeric(14, 2) as purchase_value
  from source
)

select * from renamed
