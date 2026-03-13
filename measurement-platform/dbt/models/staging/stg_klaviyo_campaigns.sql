-- stg_klaviyo_campaigns — Staging for Klaviyo campaign metrics (per-client table: {client_slug}_klaviyo_campaigns)
-- Joined with campaign_values_reports for send/open/click counts when available.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with campaigns as (
  select * from {{ source('raw_klaviyo', 'campaigns') }}
),

renamed as (
  select
    '{{ var("client_slug") }}' as client_slug,
    (attributes->>'send_time')::timestamptz::date as report_date,
    id::text as campaign_id,
    0 as sent,
    0 as opens,
    0 as clicks
  from campaigns
  where attributes->>'send_time' is not null
)

select * from renamed
