-- stg_google_spend — Staging for Google Ads daily spend (from Airbyte raw)
-- Adjust source table and column names to match your Airbyte Google Ads connector output.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_airbyte', 'account_performance_report') }}
),

renamed as (
  select
    '{{ var("client_slug") }}' as client_slug,
    date_trunc('day', (segments_date::date))::date as report_date,
    'google' as channel,
    coalesce(metrics_cost_micros::numeric(14, 2) / 1e6, 0) as spend,
    metrics_impressions::bigint as impressions,
    metrics_clicks::bigint as clicks
  from source
)

select * from renamed
