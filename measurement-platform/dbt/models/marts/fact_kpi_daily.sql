-- fact_kpi_daily — Daily revenue and orders (from Shopify staging)
{{
  config(
    materialized='table',
    schema='marts'
  )
}}

select
  client_slug,
  report_date,
  coalesce(revenue, 0) as revenue,
  coalesce(orders, 0) as orders
from {{ ref('stg_shopify_orders') }}
