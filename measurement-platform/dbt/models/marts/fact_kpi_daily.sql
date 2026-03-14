-- fact_kpi_daily — Daily revenue and orders by client (from Shopify staging)
-- Each client's orders source is tagged with a client_slug.
{{
  config(
    materialized='table',
    schema='marts'
  )
}}

with expand_orders as (
  select
    'expand' as client_slug,
    report_date,
    coalesce(revenue, 0) as revenue,
    coalesce(orders, 0) as orders
  from {{ ref('stg_shopify_orders') }}
),

chubble_orders as (
  select
    'chubble' as client_slug,
    report_date,
    coalesce(revenue, 0) as revenue,
    coalesce(orders, 0) as orders
  from {{ ref('stg_chubble_orders') }}
),

unioned as (
  select * from expand_orders
  union all
  select * from chubble_orders
)

select
  client_slug,
  report_date,
  sum(revenue) as revenue,
  sum(orders) as orders
from unioned
group by 1, 2
