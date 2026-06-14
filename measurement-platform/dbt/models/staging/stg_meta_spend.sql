-- stg_meta_spend — Staging for Meta Ads daily spend.
-- Source: raw.meta_customaccount_insights_daily (account-level daily, populated
-- by meta_sync.py via the Marketing API). One row per account per day.
-- Outputs account_id for joining with client_ad_accounts to assign client_slug.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_airbyte', 'meta_customaccount_insights_daily') }}
),

renamed as (
  select
    account_id::text as account_id,
    date_trunc('day', (date_start::date))::date as report_date,
    'meta' as channel,
    coalesce(spend::numeric(14, 2), 0) as spend,
    impressions::bigint as impressions,
    -- Use link clicks (not all clicks) for accurate CTR/CPC.
    -- all clicks includes likes, comments, shares etc.
    inline_link_clicks::bigint as clicks
  from source
)

select * from renamed
