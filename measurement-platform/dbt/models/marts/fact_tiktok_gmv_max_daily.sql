-- fact_tiktok_gmv_max_daily — Daily TikTok Shop / GMV Max performance
-- Aggregates campaign-level data to daily totals per client.
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
  count(distinct campaign_id) as active_campaigns,
  coalesce(sum(cost), 0) as cost,
  coalesce(sum(net_cost), 0) as net_cost,
  coalesce(sum(orders), 0) as orders,
  coalesce(sum(gross_revenue), 0) as gross_revenue,
  case
    when sum(orders) > 0 then sum(cost) / sum(orders)
    else 0
  end as cost_per_order,
  case
    when sum(cost) > 0 then sum(gross_revenue) / sum(cost)
    else 0
  end as roas
from {{ ref('stg_tiktok_gmv_max') }}
group by 1, 2
