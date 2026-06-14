-- stg_ga4_traffic — Staging for GA4 traffic acquisition by source/medium
-- Daily traffic breakdown per client.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_ga4', 'ga4_traffic_acquisition_session_source_medium_report') }}
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
    coalesce(s."sessionSource", '(direct)') as session_source,
    coalesce(s."sessionMedium", '(none)') as session_medium,
    coalesce(s.sessions, 0) as sessions,
    coalesce(s."totalUsers", 0) as total_users,
    coalesce(s."eventCount", 0) as event_count,
    coalesce(s."totalRevenue", 0)::numeric(14, 2) as total_revenue,
    coalesce(s."engagementRate", 0)::numeric(10, 4) as engagement_rate,
    s.property_id
  from source s
  left join property_map m on s.property_id = m.account_id
  where s.date is not null
)

select * from cleaned
