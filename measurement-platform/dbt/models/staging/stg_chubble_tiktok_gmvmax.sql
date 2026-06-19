-- stg_chubble_tiktok_gmvmax — Staging for Chubble's TikTok GMV Max campaigns (from Coupler.io)
-- Aggregates campaign-level rows to daily totals to match fact_spend_daily grain.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

{% set chubble_gmv_relation = none %}
{% if execute %}
  {% set chubble_gmv_relation = adapter.get_relation(
      database=target.database,
      schema='coupler_internal',
      identifier='tiktok_gmv_max'
  ) %}
{% endif %}

with source as (
  {% if chubble_gmv_relation is not none %}
    select * from {{ source('coupler_chubble', 'tiktok_gmv_max') }}
  {% else %}
    select
      cast(null as date) as stat_time_day,
      cast(null as numeric(14, 2)) as cost,
      cast(null as bigint) as orders,
      cast(null as numeric(14, 2)) as gross_revenue
    where 1 = 0
  {% endif %}
),

daily as (
  select
    (stat_time_day::date) as report_date,
    'tiktok' as channel,
    coalesce(sum(cost::numeric(14, 2)), 0) as spend,
    -- GMV Max doesn't expose impressions/clicks; null for now
    null::bigint as impressions,
    null::bigint as clicks,
    -- Extra GMV Max metrics (useful for ROAS / CPA analysis)
    coalesce(sum(orders::bigint), 0) as tiktok_orders,
    coalesce(sum(gross_revenue::numeric(14, 2)), 0) as tiktok_revenue
  from source
  where cost > 0 or orders::bigint > 0
  group by 1
)

select * from daily
