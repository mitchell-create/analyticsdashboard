-- fact_kpi_geo_daily — Daily revenue/orders by geography (from Shopify shipping_address)
-- Uses stg_shopify_orders_geo (province_code from shipping_address) joined to dim_geo.
{{
  config(
    materialized='table',
    schema='marts'
  )
}}

with kpi as (
  select report_date, revenue, orders from {{ ref('fact_kpi_daily') }}
),
geo as (
  select geo_id from {{ ref('dim_geo') }}
),
orders_geo as (
  select report_date, geo_id, orders, revenue
  from {{ ref('stg_shopify_orders_geo') }}
),
dates as (
  select distinct report_date from kpi
),
crossed as (
  select d.report_date, g.geo_id
  from dates d
  cross join geo g
)
select
  c.report_date,
  c.geo_id,
  coalesce(o.revenue, 0)::numeric(14, 2) as revenue,
  coalesce(o.orders, 0)::int as orders
from crossed c
left join orders_geo o on c.report_date = o.report_date and c.geo_id = o.geo_id
