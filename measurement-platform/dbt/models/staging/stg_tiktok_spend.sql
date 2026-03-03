-- stg_tiktok_spend — Staging for TikTok Ads daily spend (from Airbyte raw)
-- Adjust source table and column names to match your Airbyte TikTok connector output.

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
    '{{ var("client_slug") }}' as client_slug,
    date_trunc('day', (stat_time_day::date))::date as report_date,
    'tiktok' as channel,
    coalesce((metrics->>'spend')::numeric(14, 2), 0) as spend,
    (metrics->>'impressions')::bigint as impressions,
    (metrics->>'clicks')::bigint as clicks
  from source
)

select * from renamed
