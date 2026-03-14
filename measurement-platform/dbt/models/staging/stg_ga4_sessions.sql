-- stg_ga4_sessions — Staging for GA4 website overview
-- Daily session/engagement metrics per client.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_ga4', 'ga4_website_overview') }}
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
    coalesce(s.sessions, 0) as sessions,
    coalesce(s."newUsers", 0) as new_users,
    coalesce(s."totalUsers", 0) as total_users,
    coalesce(s."screenPageViews", 0) as pageviews,
    coalesce(s."bounceRate", 0)::numeric(10, 4) as bounce_rate,
    coalesce(s."sessionsPerUser", 0)::numeric(10, 4) as sessions_per_user,
    coalesce(s."averageSessionDuration", 0)::numeric(10, 2) as avg_session_duration,
    s.property_id
  from source s
  left join property_map m on s.property_id = m.account_id
  where s.date is not null
)

select * from cleaned
