-- stg_shopify_orders_geo — Order-level geo from shipping_address (per-client table: {client_slug}_orders)
-- Extracts province_code for US orders; aggregates daily by geo for GeoLift.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select
    created_at::date as report_date,
    coalesce(total_price::numeric(14, 2), 0) as revenue,
    upper(trim(shipping_address->>'province_code')) as province_code
   from {{ source('raw_airbyte', 'orders') }}
  where financial_status not in ('refunded', 'voided')
    and shipping_address is not null
    and coalesce(shipping_address->>'country_code', '') = 'US'
    and nullif(trim(shipping_address->>'province_code'), '') is not null
)

select
  '{{ var("client_slug") }}' as client_slug,
  report_date,
  province_code as geo_id,
  count(*)::int as orders,
  sum(revenue)::numeric(14, 2) as revenue
from source
group by report_date, province_code
