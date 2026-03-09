-- fact_klaviyo_daily — Daily Klaviyo campaign metrics
{{
  config(
    materialized='incremental',
    schema='marts',
    unique_key=['client_slug', 'report_date', 'campaign_id'],
    incremental_strategy='merge',
    on_schema_change='sync_all_columns'
  )
}}

select
  client_slug,
  report_date,
  campaign_id,
  coalesce(sent, 0) as sent,
  opens,
  clicks
from {{ ref('stg_klaviyo_campaigns') }}
