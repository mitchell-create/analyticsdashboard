-- dim_campaign — Campaign dimension (from Klaviyo + ad campaign metadata)
{{
  config(
    materialized='table',
    schema='marts'
  )
}}

with klaviyo as (
  select distinct
    client_slug,
    campaign_id,
    'klaviyo' as source,
    null::text as channel
  from {{ ref('stg_klaviyo_campaigns') }}
  where campaign_id is not null
)
select
  client_slug,
  campaign_id,
  campaign_id as campaign_name,
  source,
  channel
from klaviyo
