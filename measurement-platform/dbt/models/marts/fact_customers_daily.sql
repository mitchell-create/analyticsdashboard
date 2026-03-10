-- fact_customers_daily — Daily customer metrics (new vs returning customers)
-- Tracks new customers (first order date) and returning customers by day

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
    store_name
  from {{ ref('stg_shopify_orders_unified') }}
),

customer_first_order as (
  select
    customer_identifier,
    min(report_date) as first_order_date
  from orders
  group by customer_identifier
),

daily_customers as (
  select
    o.report_date,
    o.store_name,
    o.customer_identifier,
    cfo.first_order_date,
    case 
      when o.report_date = cfo.first_order_date then 1 
      else 0 
    end as is_new_customer,
    case 
      when o.report_date > cfo.first_order_date then 1 
      else 0 
    end as is_returning_customer
  from orders o
  left join customer_first_order cfo 
    on o.customer_identifier = cfo.customer_identifier
),

aggregated as (
  select
    report_date,
    store_name,
    count(distinct customer_identifier) as total_customers,
    sum(is_new_customer) as new_customers,
    sum(is_returning_customer) as returning_customers
  from daily_customers
  group by report_date, store_name
)

-- Aggregate across all stores for daily totals
select
  report_date,
  sum(total_customers) as total_customers,
  sum(new_customers) as new_customers,
  sum(returning_customers) as returning_customers
from aggregated
group by report_date
order by report_date
