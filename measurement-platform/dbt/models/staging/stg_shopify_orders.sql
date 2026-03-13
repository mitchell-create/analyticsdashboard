-- stg_shopify_orders — Staging for Shopify orders (from Airbyte raw); aggregated to daily revenue/orders
-- Adjust source table and column names to match your Airbyte Shopify connector output.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_airbyte', 'expand_orders') }}
),

daily as (
  select
    'expand' as client_slug,
    (created_at::date) as report_date,
    count(*) as orders,
    coalesce(sum(total_price::numeric(14, 2)), 0) as revenue
  from source
  where financial_status not in ('refunded', 'voided')
  group by 1, 2
)

select client_slug, report_date, orders, revenue from daily
