-- fact_tiktok_gmvmax_daily — TikTok Shop / GMV Max daily performance.
-- Exposes orders, revenue, cost per order and ROAS from the Coupler.io staging model.
-- Currently hard-coded to chubble; extend with client_ad_accounts when more clients use GMV Max.
{{
  config(
    materialized='view',
    schema='marts'
  )
}}

select
  'chubble' as client_slug,
  report_date,
  spend,
  tiktok_orders as orders,
  tiktok_revenue as revenue,
  case when tiktok_orders > 0
    then round((spend / tiktok_orders)::numeric, 2)
    else null
  end as cost_per_order,
  case when spend > 0
    then round((tiktok_revenue / spend)::numeric, 2)
    else null
  end as roas
from {{ ref('stg_chubble_tiktok_gmvmax') }}
