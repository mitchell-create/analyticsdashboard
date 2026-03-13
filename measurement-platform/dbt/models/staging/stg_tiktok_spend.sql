-- stg_tiktok_spend — Staging for TikTok Ads daily spend
-- Shared table (all clients); derives client_slug from advertiser_id via client_ad_accounts seed.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
    select * from {{ source('raw_airbyte', 'tiktok_advertisers_reports_daily') }}
),

account_map as (
  select account_id, client_slug
  from {{ ref('client_ad_accounts') }}
  where platform = 'tiktok'
),

renamed as (
  select
    coalesce(m.client_slug, '{{ var("client_slug") }}') as client_slug,
    date_trunc('day', (s.stat_time_day::date))::date as report_date,
    'tiktok' as channel,
    coalesce((s.metrics->>'spend')::numeric(14, 2), 0) as spend,
    (s.metrics->>'impressions')::bigint as impressions,
    (s.metrics->>'clicks')::bigint as clicks
  from source s
  left join account_map m on s.advertiser_id::text = m.account_id
)

select * from renamed
