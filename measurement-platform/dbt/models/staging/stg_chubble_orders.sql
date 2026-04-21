-- stg_chubble_orders — Staging for Chubble Shopify orders (from Airbyte raw)
-- Aggregated to daily revenue/orders (same pattern as Expand's stg_shopify_orders).

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

{% set chubble_orders_relation = none %}
{% if execute %}
  {% set chubble_orders_relation = adapter.get_relation(
      database=target.database,
      schema=var('raw_schema', 'raw'),
      identifier='chubble_orders'
  ) %}
{% endif %}

with source as (
  {% if chubble_orders_relation is not none %}
    select * from {{ source('raw_chubble', 'chubble_orders') }}
  {% else %}
    select
      cast(null as timestamp) as created_at,
      cast(null as text) as financial_status,
      cast(null as numeric(14, 2)) as total_price
    where 1 = 0
  {% endif %}
),

daily as (
  select
    (created_at::date) as report_date,
    count(*) as orders,
    coalesce(sum(total_price::numeric(14, 2)), 0) as revenue
  from source
  where financial_status in ('paid', 'partially_paid')
  group by 1
)

select * from daily
