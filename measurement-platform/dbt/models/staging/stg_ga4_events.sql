-- stg_ga4_events — Staging for GA4 events report
-- Pivots event-level rows into daily funnel metrics per client.
-- Maps property_id to client_slug via client_ad_accounts seed.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_ga4', 'ga4_events_report') }}
),

property_map as (
  select account_id, client_slug
  from {{ ref('client_ad_accounts') }}
  where platform = 'ga4'
),

cleaned as (
  select
    coalesce(m.client_slug, 'unknown') as client_slug,
    to_date(s.date, 'YYYYMMDD') as report_date,
    s."eventName" as event_name,
    coalesce(s."eventCount", 0) as event_count,
    coalesce(s."totalUsers", 0) as total_users,
    coalesce(s."totalRevenue", 0)::numeric(14, 2) as total_revenue,
    coalesce(s."eventCountPerUser", 0)::numeric(10, 4) as event_count_per_user,
    s.property_id
  from source s
  left join property_map m on s.property_id = m.account_id
  where s.date is not null
)

select * from cleaned
