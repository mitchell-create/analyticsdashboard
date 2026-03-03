-- stg_meta_spend — Staging for Meta Ads daily spend
-- Shared table (all clients); derives client_slug from account_id via client_ad_accounts seed.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_shared', 'ads_insights') }}
),

account_map as (
  select account_id, client_slug
  from {{ ref('client_ad_accounts') }}
  where platform = 'meta'
),

renamed as (
  select
    coalesce(m.client_slug, '{{ var("client_slug") }}') as client_slug,
    date_trunc('day', (s.date_start::date))::date as report_date,
    'meta' as channel,
    coalesce(s.spend::numeric(14, 2), 0) as spend,
    s.impressions::bigint as impressions,
    s.clicks::bigint as clicks
  from source s
  left join account_map m on s.account_id::text = m.account_id
)

select * from renamed
