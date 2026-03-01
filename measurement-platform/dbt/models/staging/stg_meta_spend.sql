-- stg_meta_spend — Staging for Meta Ads daily spend (from Airbyte raw)
-- Adjust source table and column names to match your Airbyte Meta connector output.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_airbyte', 'ads_insights') }}
),

renamed as (
  select
    date_trunc('day', (date_start::date))::date as report_date,
    'meta' as channel,
    coalesce(spend::numeric(14, 2), 0) as spend,
    impressions::bigint as impressions,
    clicks::bigint as clicks
  from source
)

select * from renamed
