-- fact_klaviyo_daily — Daily Klaviyo campaign and flow metrics (multi-client)
{{
  config(
    materialized='table',
    schema='marts'
  )
}}

with campaigns as (
  select
    client_slug,
    report_date,
    campaign_id,
    null::text as flow_id,
    'campaign' as record_type,
    sent,
    opens,
    clicks,
    bounced,
    unsubscribes,
    spam_complaints,
    recipients,
    conversions,
    revenue,
    revenue_per_recipient,
    open_rate,
    click_rate,
    bounce_rate,
    unsubscribe_rate,
    delivery_rate,
    click_to_open_rate,
    conversion_rate
  from {{ ref('stg_klaviyo_campaigns') }}
),

flows as (
  select
    client_slug,
    report_date,
    null::text as campaign_id,
    flow_id,
    'flow' as record_type,
    sent,
    opens,
    clicks,
    bounced,
    unsubscribes,
    spam_complaints,
    recipients,
    conversions,
    revenue,
    revenue_per_recipient,
    -- Flows don't have pre-computed rates; compute in Metabase from counts
    null::numeric as open_rate,
    null::numeric as click_rate,
    null::numeric as bounce_rate,
    null::numeric as unsubscribe_rate,
    null::numeric as delivery_rate,
    null::numeric as click_to_open_rate,
    null::numeric as conversion_rate
  from {{ ref('stg_klaviyo_flows') }}
)

select * from campaigns
union all
select * from flows
