-- stg_tiktok_gmv_max — Staging for TikTok Shop / GMV Max campaign data
-- Source: coupler.io → coupler_internal.tiktok_gmv_max
-- Currently Chubble Gum only; extend client_slug mapping as more stores are added.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

{% set tiktok_gmv_max_relation = none %}
{% if execute %}
  {% set tiktok_gmv_max_relation = adapter.get_relation(
      database=target.database,
      schema='coupler_internal',
      identifier='tiktok_gmv_max'
  ) %}
{% endif %}

with source as (
  {% if tiktok_gmv_max_relation is not none %}
    select * from {{ source('coupler_chubble', 'tiktok_gmv_max') }}
  {% else %}
    select
      cast(null as text) as ad_account_name,
      cast(null as date) as stat_time_day,
      cast(null as text) as store_name,
      cast(null as text) as store_id,
      cast(null as bigint) as campaign_id,
      cast(null as text) as campaign_name,
      cast(null as numeric(14, 2)) as cost,
      cast(null as numeric(14, 2)) as net_cost,
      cast(null as bigint) as orders,
      cast(null as numeric(14, 2)) as cost_per_order,
      cast(null as numeric(14, 2)) as gross_revenue,
      cast(null as numeric(10, 4)) as roi
    where 1 = 0
  {% endif %}
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
