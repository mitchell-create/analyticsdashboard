-- stg_klaviyo_campaigns — Staging for Klaviyo campaign metrics (from Airbyte raw)
-- Adjust source table and column names to match your Airbyte Klaviyo connector output.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_airbyte', 'klaviyo_campaigns') }}
),

renamed as (
  select
    (attributes->>'send_time')::timestamptz::date as report_date,
    id::text as campaign_id,
    0 as sent,
    0 as opens,
    0 as clicks
  from source
  where attributes->>'send_time' is not null
  -- Klaviyo campaigns stream has attributes JSONB; sent/opens/clicks need metrics stream or different sync
)

select * from renamed
