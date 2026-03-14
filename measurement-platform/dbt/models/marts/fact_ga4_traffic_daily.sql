-- fact_ga4_traffic_daily — Daily traffic by source/medium from GA4
-- Attributes sessions and revenue to traffic channels.
{{
  config(
    materialized='incremental',
    schema='marts',
    unique_key=['client_slug', 'report_date', 'session_source', 'session_medium'],
    incremental_strategy='merge',
    on_schema_change='sync_all_columns'
  )
}}

select
  client_slug,
  report_date,
  session_source,
  session_medium,
  sum(sessions) as sessions,
  sum(total_users) as total_users,
  sum(event_count) as event_count,
  sum(total_revenue) as total_revenue,
  avg(engagement_rate) as avg_engagement_rate
from {{ ref('stg_ga4_traffic') }}
group by 1, 2, 3, 4
