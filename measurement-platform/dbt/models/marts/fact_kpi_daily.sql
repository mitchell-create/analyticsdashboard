-- fact_kpi_daily — Daily revenue and orders by client
-- Sources: Shopify (expand, chubble, crazy_rumors, zoka) + GA4 purchases (babybay)
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

crazy_rumors_orders as (
  select
    'crazy_rumors' as client_slug,
    report_date,
    coalesce(revenue, 0) as revenue,
    coalesce(orders, 0) as orders
  from {{ ref('stg_crazy_rumors_orders') }}
),

zoka_orders as (
  select
    'zoka' as client_slug,
    report_date,
    coalesce(revenue, 0) as revenue,
    coalesce(orders, 0) as orders
  from {{ ref('stg_zoka_orders') }}
),

-- babybay uses GA4 (no Shopify)
ga4_orders as (
  select
    client_slug,
    report_date,
    coalesce(purchase_revenue, 0) as revenue,
    coalesce(purchases, 0) as orders
  from {{ ref('fact_ga4_funnel_daily') }}
  where client_slug = 'babybay'
),

unioned as (
  select * from expand_orders
  union all
  select * from chubble_orders
  union all
  select * from crazy_rumors_orders
  union all
  select * from zoka_orders
  union all
  select * from ga4_orders
)

select
  client_slug,
  report_date,
  sum(revenue) as revenue,
  sum(orders) as orders
from unioned
group by 1, 2
