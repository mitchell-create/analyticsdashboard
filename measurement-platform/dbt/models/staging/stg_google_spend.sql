-- stg_google_spend — Staging for Google Ads daily spend
-- Shared table (all clients); derives client_slug from customer_id via client_ad_accounts seed.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_shared', 'google_campaign') }}
),

account_map as (
  select account_id, client_slug
  from {{ ref('client_ad_accounts') }}
  where platform = 'google'
),

renamed as (
  select
    coalesce(m.client_slug, '{{ var("client_slug") }}') as client_slug,
    date_trunc('day', (s.segments_date::date))::date as report_date,
    'google' as channel,
    coalesce(s.metrics_cost_micros::numeric(14, 2) / 1e6, 0) as spend,
    s.metrics_impressions::bigint as impressions,
    s.metrics_clicks::bigint as clicks
  from source s
  left join account_map m on s.customer_id::text = m.account_id
)

select * from renamed
