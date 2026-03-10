-- stg_shopify_orders_unified — Unified staging for all Shopify orders (chubble + expand)
-- Combines orders from multiple stores into a single unified view

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with chubble_orders as (
  select
    id,
    email,
    customer,
    created_at,
    total_price,
    financial_status,
    'chubble' as store_name
  from {{ source('raw_airbyte', 'chubble_orders') }}
  where financial_status in ('paid', 'partially_paid')
),

expand_orders as (
  select
    id,
    email,
    customer,
    created_at,
    total_price,
    financial_status,
    'expand' as store_name
  from {{ source('raw_airbyte', 'expand_orders') }}
  where financial_status in ('paid', 'partially_paid')
),

unified_orders as (
  select * from chubble_orders
  union all
  select * from expand_orders
)

select
  id,
  email,
  customer,
  created_at,
  created_at::date as report_date,
  total_price,
  financial_status,
  store_name,
  -- Customer identifier: prefer email, fallback to customer ID
  coalesce(email, customer::text) as customer_identifier
from unified_orders
