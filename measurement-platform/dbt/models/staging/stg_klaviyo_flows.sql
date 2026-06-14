-- stg_klaviyo_flows — Staging for Klaviyo flow series reports (multi-client)
-- Sources: raw.{client}_klaviyo_flow_series_reports (via klaviyo_sync.py)
-- Statistics values are JSON arrays (one element per day/month in the interval).
-- We sum the array to get the total for the period.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

{% set clients = ['expand', 'chubble', 'crazy_rumors', 'zoka', 'babybay'] %}

{% for client in clients %}
select
  '{{ client }}' as client_slug,
  (date::timestamptz)::date as report_date,
  flow_id::text as flow_id,
  flow_message_id::text as flow_message_id,
  coalesce((
    select sum(v::numeric)::int from jsonb_array_elements_text(statistics->'delivered') as v
  ), 0) as sent,
  coalesce((
    select sum(v::numeric)::int from jsonb_array_elements_text(statistics->'opens') as v
  ), 0) as opens,
  coalesce((
    select sum(v::numeric)::int from jsonb_array_elements_text(statistics->'clicks') as v
  ), 0) as clicks,
  coalesce((
    select sum(v::numeric)::int from jsonb_array_elements_text(statistics->'bounced') as v
  ), 0) as bounced,
  coalesce((
    select sum(v::numeric)::int from jsonb_array_elements_text(statistics->'unsubscribes') as v
  ), 0) as unsubscribes,
  coalesce((
    select sum(v::numeric)::int from jsonb_array_elements_text(statistics->'spam_complaints') as v
  ), 0) as spam_complaints,
  coalesce((
    select sum(v::numeric)::int from jsonb_array_elements_text(statistics->'recipients') as v
  ), 0) as recipients,
  coalesce((
    select sum(v::numeric)::int from jsonb_array_elements_text(statistics->'conversions') as v
  ), 0) as conversions,
  coalesce((
    select sum(v::numeric) from jsonb_array_elements_text(statistics->'conversion_value') as v
  ), 0) as revenue,
  coalesce((
    select sum(v::numeric) from jsonb_array_elements_text(statistics->'revenue_per_recipient') as v
  ), 0) as revenue_per_recipient
from {{ source('raw_klaviyo', client ~ '_klaviyo_flow_series_reports') }}
where date is not null
{% if not loop.last %}union all{% endif %}
{% endfor %}
