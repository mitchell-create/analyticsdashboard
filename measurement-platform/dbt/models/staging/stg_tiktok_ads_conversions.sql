-- stg_tiktok_ads_conversions — Staging for TikTok Ads WEBSITE conversion metrics
-- Source: tiktok_ads_reports_daily (ad-level daily data)
-- Revenue = value_per_complete_payment * complete_payment (per ad row, then summed)
-- complete_payment = WEBSITE conversions only (confirmed via TikTok Pixel)
-- TikTok Shop data is in a SEPARATE pipeline: coupler.io → fact_tiktok_gmv_max_daily

{{
    config(
      materialized='view',
      schema='staging'
    )
  }}

with source as (
    select * from {{ source('raw_tiktok_ads', 'tiktok_ads_reports_daily') }}
  ),

account_map as (
    select account_id, client_slug
    from {{ ref('client_ad_accounts') }}
    where platform = 'tiktok'
  ),

cleaned as (
    select
      coalesce(m.client_slug, '{{ var("client_slug") }}') as client_slug,
      (s.stat_time_day::date) as report_date,
      s.ad_id,
      s.adgroup_id,
      s.campaign_id,
      s.advertiser_id,

    -- Ad metadata from metrics JSON
    (s.metrics->>'campaign_name') as campaign_name,
      (s.metrics->>'adgroup_name') as adgroup_name,
      (s.metrics->>'ad_name') as ad_name,

    -- Spend & traffic
    coalesce((s.metrics->>'spend')::numeric(14, 2), 0) as spend,
      coalesce((s.metrics->>'clicks')::numeric, 0)::bigint as clicks,
      coalesce((s.metrics->>'impressions')::numeric, 0)::bigint as impressions,

    -- Website conversions (from TikTok Pixel — does NOT include TikTok Shop)
    coalesce((s.metrics->>'complete_payment')::numeric, 0)::bigint as website_purchases,
      coalesce(
        (s.metrics->>'value_per_complete_payment')::numeric
        * (s.metrics->>'complete_payment')::numeric,
        0
      )::numeric(14, 2) as website_revenue,
      coalesce((s.metrics->>'value_per_complete_payment')::numeric(14, 2), 0) as avg_order_value,

    -- Combined conversions
    coalesce((s.metrics->>'conversion')::numeric, 0)::bigint as total_conversions,

    -- Attribution breakdown
    coalesce((s.metrics->>'cta_purchase')::numeric, 0) as click_through_purchases,
      coalesce((s.metrics->>'vta_purchase')::numeric, 0) as view_through_purchases,
      coalesce((s.metrics->>'cta_conversion')::numeric, 0) as click_through_conversions,
      coalesce((s.metrics->>'vta_conversion')::numeric, 0) as view_through_conversions,

    -- Funnel metrics
    coalesce((s.metrics->>'total_app_event_add_to_cart')::numeric, 0)::bigint as add_to_carts,
      coalesce((s.metrics->>'total_pageview')::numeric, 0)::bigint as pageviews,

    -- Engagement
    coalesce((s.metrics->>'video_play_actions')::numeric, 0)::bigint as video_plays,
      coalesce((s.metrics->>'engagements')::numeric, 0)::bigint as engagements,
      coalesce((s.metrics->>'likes')::numeric, 0)::bigint as likes,
      coalesce((s.metrics->>'shares')::numeric, 0)::bigint as shares,
      coalesce((s.metrics->>'comments')::numeric, 0)::bigint as comments

    from source s
    left join account_map m on s.advertiser_id::text = m.account_id
    where s.stat_time_day is not null
  )

select * from cleaned
