-- fact_ga4_funnel_daily — Daily funnel metrics from GA4
-- Pivots events into columns: sessions, add_to_cart, begin_checkout, purchase, etc.
{{
  config(
    materialized='incremental',
    schema='marts',
    unique_key=['client_slug', 'report_date'],
    incremental_strategy='merge',
    on_schema_change='sync_all_columns'
  )
}}

with events as (
  select * from {{ ref('stg_ga4_events') }}
),

sessions as (
  select * from {{ ref('stg_ga4_sessions') }}
),

funnel as (
  select
    client_slug,
    report_date,
    sum(case when event_name = 'session_start' then event_count else 0 end) as sessions,
    sum(case when event_name = 'page_view' then event_count else 0 end) as page_views,
    sum(case when event_name = 'view_item' then event_count else 0 end) as product_views,
    sum(case when event_name = 'view_item_list' then event_count else 0 end) as product_list_views,
    sum(case when event_name = 'add_to_cart' then event_count else 0 end) as add_to_carts,
    sum(case when event_name = 'view_cart' then event_count else 0 end) as cart_views,
    sum(case when event_name = 'begin_checkout' then event_count else 0 end) as checkouts,
    sum(case when event_name = 'purchase' then event_count else 0 end) as purchases,
    sum(case when event_name = 'purchase' then total_revenue else 0 end) as purchase_revenue,

    -- Unique users at each funnel step
    sum(case when event_name = 'session_start' then total_users else 0 end) as session_users,
    sum(case when event_name = 'add_to_cart' then total_users else 0 end) as atc_users,
    sum(case when event_name = 'begin_checkout' then total_users else 0 end) as checkout_users,
    sum(case when event_name = 'purchase' then total_users else 0 end) as purchase_users
  from events
  group by 1, 2
),

enriched as (
  select
    f.*,
    s.new_users,
    s.total_users,
    s.pageviews as total_pageviews,
    s.bounce_rate,
    s.avg_session_duration,

    -- Funnel conversion rates
    case when f.sessions > 0 then f.add_to_carts::numeric / f.sessions else 0 end as session_to_atc_rate,
    case when f.add_to_carts > 0 then f.checkouts::numeric / f.add_to_carts else 0 end as atc_to_checkout_rate,
    case when f.checkouts > 0 then f.purchases::numeric / f.checkouts else 0 end as checkout_to_purchase_rate,
    case when f.sessions > 0 then f.purchases::numeric / f.sessions else 0 end as overall_conversion_rate
  from funnel f
  left join sessions s on f.client_slug = s.client_slug and f.report_date = s.report_date
)

select * from enriched
