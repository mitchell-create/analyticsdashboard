-- stg_zoka_orders — Staging for Zoka Shopify orders (from Airbyte raw)
-- Aggregated to daily revenue/orders (same pattern as Expand/Chubble).

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_zoka', 'zoka_orders') }}
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
