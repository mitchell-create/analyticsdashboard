-- stg_shopify_orders — Staging for Shopify orders (from Airbyte raw); aggregated to daily revenue/orders
-- Adjust source table and column names to match your Airbyte Shopify connector output.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_airbyte', 'orders') }}
),

daily as (
  select
    '{{ var("client_slug") }}' as client_slug,
    (created_at::date) as report_date,
    count(*) as orders,
    coalesce(sum(total_price::numeric(14, 2)), 0) as revenue
  from source
  where financial_status in ('paid', 'partially_paid')
  group by 1
)

select * from daily
