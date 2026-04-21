-- stg_tiktok_gmv — Staging for TikTok GMV Max daily report (from Coupler.io)
-- Adjust column names below to match Coupler's TikTok connector output.
-- Common TikTok GMV API columns: stat_time_day, total_purchase_value, total_purchase, cost.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

{% set tiktok_gmv_max_relation = none %}
{% if execute %}
  {% set tiktok_gmv_max_relation = adapter.get_relation(
      database=target.database,
      schema='coupler_internal',
      identifier='tiktok_gmv_max'
  ) %}
{% endif %}

with source as (
  {% if tiktok_gmv_max_relation is not none %}
    select * from {{ source('coupler_chubble', 'tiktok_gmv_max') }}
  {% else %}
    select
      cast(null as timestamp) as stat_time_day,
      cast(null as numeric(14, 2)) as total_purchase_value,
      cast(null as int) as total_purchase,
      cast(null as numeric(14, 2)) as cost
    where 1 = 0
  {% endif %}
),

renamed as (
  select
    date_trunc('day', (stat_time_day::date))::date as report_date,
    coalesce((total_purchase_value)::numeric(14, 2), 0) as gmv,
    coalesce((total_purchase)::int, 0) as orders,
    coalesce((cost)::numeric(14, 2), 0) as spend
  from source
)

select * from renamed
