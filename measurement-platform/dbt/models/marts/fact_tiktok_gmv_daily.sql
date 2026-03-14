-- fact_tiktok_gmv_daily — Daily TikTok GMV (from Coupler.io GMV Max report)
-- Aggregates staging to one row per day for dashboards and reporting.

{{
  config(
    materialized='table',
    schema='marts'
  )
}}

select
  report_date,
  sum(gmv) as gmv,
  sum(orders) as orders,
  sum(spend) as spend
from {{ ref('stg_tiktok_gmv') }}
group by report_date
order by report_date
