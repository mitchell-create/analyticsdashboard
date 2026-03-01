-- fact_klaviyo_daily — Daily Klaviyo campaign metrics
{{
  config(
    materialized='table',
    schema='marts'
  )
}}

select
  report_date,
  campaign_id,
  coalesce(sent, 0) as sent,
  opens,
  clicks
from {{ ref('stg_klaviyo_campaigns') }}
