-- stg_tiktok_gmv_max — Staging for TikTok Shop / GMV Max campaign data
-- Source: coupler.io → coupler_internal.tiktok_gmv_max
-- Currently Chubble Gum only; extend client_slug mapping as more stores are added.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('coupler_tiktok', 'tiktok_gmv_max') }}
),

renamed as (
  select
    -- Derive client_slug from ad_account_name
    case lower(trim(ad_account_name))
      when 'chubblegum' then 'chubble'
      else lower(trim(ad_account_name))
    end as client_slug,

    (stat_time_day::date) as report_date,
    store_name,
    store_id,
    campaign_id::bigint as campaign_id,
    campaign_name,

    'tiktok_shop' as channel,

    coalesce(cost, 0)::numeric(14, 2) as cost,
    coalesce(net_cost, 0)::numeric(14, 2) as net_cost,
    coalesce(orders, 0)::bigint as orders,
    coalesce(cost_per_order, 0)::numeric(14, 2) as cost_per_order,
    coalesce(gross_revenue, 0)::numeric(14, 2) as gross_revenue,
    coalesce(roi, 0)::numeric(10, 4) as roi
  from source
  where stat_time_day is not null
)

select * from renamed
