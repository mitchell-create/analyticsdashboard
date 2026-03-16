-- stg_shopify_orders — Staging for Shopify orders (from Airbyte raw); aggregated to daily revenue/orders
-- Revenue matches Shopify "Total Sales": SUM(total_price) for all completed orders minus refund amounts
-- processed that day. Order count excludes fully refunded orders (matching Shopify's order count).
-- Refund amounts in non-shop currency are converted using the order's exchange rate.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_expand', 'expand_orders') }}
),

-- Order revenue by creation date (total_price includes tax + shipping)
-- Gross revenue includes ALL completed orders (incl. refunded) so refunds net out correctly
-- Order count excludes fully refunded orders to match Shopify's order metric
order_revenue as (
  select
    (created_at::date) as report_date,
    count(*) filter (where financial_status in ('paid', 'partially_paid', 'partially_refunded')) as orders,
    coalesce(sum(total_price::numeric(14, 2)), 0) as gross_revenue
  from source
  where financial_status in ('paid', 'partially_paid', 'partially_refunded', 'refunded')
  group by 1
),

-- Refund amounts by processed date, converted to shop currency (USD)
-- Each refund has transactions with amounts in presentment currency
refund_amounts as (
  select
    (r.value->>'processed_at')::date as refund_date,
    sum(
      case
        when t.value->>'currency' = 'USD'
          then (t.value->>'amount')::numeric
        else (t.value->>'amount')::numeric
          * (s.total_price::numeric / nullif((s.total_price_set->'presentment_money'->>'amount')::numeric, 0))
      end
    ) as refund_total
  from source s,
    jsonb_array_elements(s.refunds) r,
    jsonb_array_elements(r.value->'transactions') t
  where t.value->>'kind' = 'refund'
    and t.value->>'status' = 'success'
    and (t.value->>'amount')::numeric > 0
  group by 1
),

daily as (
  select
    coalesce(o.report_date, rf.refund_date) as report_date,
    coalesce(o.orders, 0) as orders,
    greatest(coalesce(o.gross_revenue, 0) - coalesce(rf.refund_total, 0), 0) as revenue
  from order_revenue o
  full outer join refund_amounts rf on rf.refund_date = o.report_date
)

select * from daily
