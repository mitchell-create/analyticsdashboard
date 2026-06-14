-- stg_klaviyo_campaigns — Staging for Klaviyo campaign metrics (multi-client)
-- Sources: raw.{client}_klaviyo_campaign_values_reports (via klaviyo_sync.py)
-- Statistics are nested in a JSONB `statistics` column (scalar floats).

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
  campaign_id::text as campaign_id,
  coalesce((statistics->>'delivered')::numeric::int, 0) as sent,
  coalesce((statistics->>'opens')::numeric::int, 0) as opens,
  coalesce((statistics->>'clicks')::numeric::int, 0) as clicks,
  coalesce((statistics->>'bounced')::numeric::int, 0) as bounced,
  coalesce((statistics->>'unsubscribes')::numeric::int, 0) as unsubscribes,
  coalesce((statistics->>'spam_complaints')::numeric::int, 0) as spam_complaints,
  coalesce((statistics->>'recipients')::numeric::int, 0) as recipients,
  coalesce((statistics->>'conversions')::numeric::int, 0) as conversions,
  coalesce((statistics->>'conversion_value')::numeric, 0) as revenue,
  coalesce((statistics->>'revenue_per_recipient')::numeric, 0) as revenue_per_recipient,
  coalesce((statistics->>'open_rate')::numeric, 0) as open_rate,
  coalesce((statistics->>'click_rate')::numeric, 0) as click_rate,
  coalesce((statistics->>'bounce_rate')::numeric, 0) as bounce_rate,
  coalesce((statistics->>'unsubscribe_rate')::numeric, 0) as unsubscribe_rate,
  coalesce((statistics->>'delivery_rate')::numeric, 0) as delivery_rate,
  coalesce((statistics->>'click_to_open_rate')::numeric, 0) as click_to_open_rate,
  coalesce((statistics->>'conversion_rate')::numeric, 0) as conversion_rate
from {{ source('raw_klaviyo', client ~ '_klaviyo_campaign_values_reports') }}
where date is not null
{% if not loop.last %}union all{% endif %}
{% endfor %}
