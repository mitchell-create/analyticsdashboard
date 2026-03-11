-- stg_shopify_orders_unified — Unified staging for all Shopify/WooCommerce orders
-- Combines orders from all stores into a single unified view
-- Note: Add more stores as their tables become available

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

-- Uncomment these as the tables become available:
-- babybay_orders as (
--   select
--     id,
--     email,
--     customer,
--     created_at,
--     total_price,
--     financial_status,
--     'babybay' as store_name
--   from {{ source('raw_airbyte', 'orders_babybay') }}
--   where financial_status in ('paid', 'partially_paid')
-- ),

-- crazyrumors_orders as (
--   select
--     id,
--     email,
--     customer,
--     created_at,
--     total_price,
--     financial_status,
--     'crazyrumors' as store_name
--   from {{ source('raw_airbyte', 'orders_crazyrumors') }}
--   where financial_status in ('paid', 'partially_paid')
-- ),

-- zoka_orders as (
--   select
--     id,
--     email,
--     customer,
--     created_at,
--     total_price,
--     financial_status,
--     'zoka' as store_name
--   from {{ source('raw_airbyte', 'orders_zoka') }}
--   where financial_status in ('paid', 'partially_paid')
-- ),

-- motive_orders as (
--   select
--     id,
--     email,
--     customer,
--     created_at,
--     total_price,
--     financial_status,
--     'motive' as store_name
--   from {{ source('raw_airbyte', 'orders_motive') }}
--   where financial_status in ('paid', 'partially_paid')
-- ),

unified_orders as (
  select * from chubble_orders
  union all
  select * from expand_orders
  -- Uncomment as tables become available:
  -- union all
  -- select * from babybay_orders
  -- union all
  -- select * from crazyrumors_orders
  -- union all
  -- select * from zoka_orders
  -- union all
  -- select * from motive_orders
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