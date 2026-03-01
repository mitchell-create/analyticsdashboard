-- fact_tiktok_organic_daily — Daily TikTok organic metrics (from Metricool staging)
{{
  config(
    materialized='table',
    schema='marts'
  )
}}

select
  report_date,
  coalesce(views, 0) as views,
  likes,
  comments,
  shares,
  followers
from {{ ref('stg_metricool_tiktok') }}
