-- stg_google_spend — Staging for Google Ads daily spend
-- Shared table (all clients); derives client_slug from customer_id extracted
-- from campaign_resource_name (format: 'customers/CUSTOMER_ID/campaigns/...')

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_airbyte', 'account_performance_report') }}
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
  left join account_map m
    on split_part(s.campaign_resource_name, '/', 2) = m.account_id
)

select * from renamed
