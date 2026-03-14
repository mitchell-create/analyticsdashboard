-- stg_tiktok_spend — Staging for TikTok Ads daily spend (from Airbyte raw)
-- Outputs account_id (advertiser_id) for joining with client_ad_accounts to assign client_slug.
-- This covers regular TikTok ads (web conversions). GMV Max is separate (stg_chubble_tiktok_gmvmax).

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
    advertiser_id::text as account_id,
    date_trunc('day', (stat_time_day::date))::date as report_date,
    'tiktok' as channel,
    coalesce((metrics->>'spend')::numeric(14, 2), 0) as spend,
    (metrics->>'impressions')::bigint as impressions,
    (metrics->>'clicks')::bigint as clicks
  from source
)

select * from renamed
