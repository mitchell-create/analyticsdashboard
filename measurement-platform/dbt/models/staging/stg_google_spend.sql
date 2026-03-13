-- stg_google_spend — Staging for Google Ads daily spend (from Airbyte raw)
-- Outputs account_id (customer_id) for joining with client_ad_accounts to assign client_slug.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_airbyte', 'google_account_performance_report') }}
),

renamed as (
  select
    customer_id::text as account_id,
    date_trunc('day', (segments_date::date))::date as report_date,
    'google' as channel,
    coalesce(metrics_cost_micros::numeric(14, 2) / 1e6, 0) as spend,
    metrics_impressions::bigint as impressions,
    metrics_clicks::bigint as clicks
  from source
)

select * from renamed
