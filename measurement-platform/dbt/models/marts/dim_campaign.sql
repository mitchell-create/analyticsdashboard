-- dim_campaign — Campaign dimension (from Klaviyo + ad campaign metadata)
{{
  config(
    materialized='table',
    schema='marts'
  )
}}

with klaviyo as (
  select distinct
    campaign_id,
    'klaviyo' as source,
    null::text as channel
  from {{ ref('stg_klaviyo_campaigns') }}
  where campaign_id is not null
)
select
  campaign_id,
  campaign_id as campaign_name,
  source,
  channel
from klaviyo
union
-- Placeholder for ad campaigns (Meta/Google/TikTok campaign IDs when available)
select
  'unknown' as campaign_id,
  'Unknown' as campaign_name,
  'manual' as source,
  null::text as channel
where false
