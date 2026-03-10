-- dim_customers — Customer dimension table
-- Tracks each unique customer with their first order date and lifetime metrics

{{
  config(
    materialized='table',
    schema='marts'
  )
}}

with orders as (
  select
    customer_identifier,
    report_date,
    store_name,
    total_price
  from {{ ref('stg_shopify_orders_unified') }}
),

customer_metrics as (
  select
    customer_identifier,
    min(report_date) as first_order_date,
    max(report_date) as last_order_date,
    count(distinct report_date) as days_with_orders,
    count(*) as total_orders,
    sum(total_price::numeric) as lifetime_revenue
  from orders
  group by customer_identifier
)

select
  customer_identifier,
  first_order_date,
  last_order_date,
  days_with_orders,
  total_orders,
  lifetime_revenue,
  -- Calculate if customer is new (first order in last year)
  case 
    when first_order_date >= current_date - interval '1 year' then true 
    else false 
  end as is_new_customer_last_year,
  -- Calculate days since first order
  current_date - first_order_date as days_since_first_order
from customer_metrics
order by first_order_date desc
