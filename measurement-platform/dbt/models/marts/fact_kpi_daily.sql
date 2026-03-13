-- fact_kpi_daily — Daily revenue and orders (from Shopify staging)
{{
  config(
    materialized='incremental',
    schema='marts',
    unique_key=['client_slug', 'report_date'],
    incremental_strategy='merge',
    on_schema_change='sync_all_columns'
  )
}}

select
  client_slug,
  report_date,
  coalesce(revenue, 0) as revenue,
  coalesce(orders, 0) as orders
from {{ ref('stg_shopify_orders') }}
