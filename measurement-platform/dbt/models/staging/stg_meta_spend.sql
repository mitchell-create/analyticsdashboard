-- stg_meta_spend — Staging for Meta Ads daily spend + purchase value (from Airbyte raw)
-- Extracts spend, impressions, clicks, and purchase_value from ads_insights.
-- Meta purchase_value comes from action_values (action_type = 'omni_purchase' or 'purchase').

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
    clicks::bigint as clicks,
    -- Extract purchase value from action_values JSON array
    -- Meta reports this as action_values[].value where action_type in ('omni_purchase', 'purchase')
    coalesce(
      (
        select sum((elem->>'value')::numeric(14, 2))
        from jsonb_array_elements(
          case
            when jsonb_typeof(action_values::jsonb) = 'array' then action_values::jsonb
            else '[]'::jsonb
          end
        ) as elem
        where elem->>'action_type' in ('omni_purchase', 'purchase')
      ),
      0
    )::numeric(14, 2) as purchase_value
  from source
)

select * from renamed
