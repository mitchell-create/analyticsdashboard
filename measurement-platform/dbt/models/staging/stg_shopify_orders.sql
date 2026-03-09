-- stg_shopify_orders — Staging for Shopify orders (per-client table: {client_slug}_orders)
-- Aggregated to daily revenue/orders.
-- Revenue = total_price (matches Shopify's "Total Sales" = net sales + shipping + tax)
-- Excludes fully refunded and voided orders; keeps partially_refunded.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_shopify', 'orders') }}
),

daily as (
  select
    '{{ var("client_slug") }}' as client_slug,
    (created_at::date) as report_date,
    count(*) as orders,
    coalesce(sum(total_price::numeric(14, 2)), 0) as revenue
  from source
  where financial_status not in ('refunded', 'voided')
  group by 1, 2
)

select * from daily
