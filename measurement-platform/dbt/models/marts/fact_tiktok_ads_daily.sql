-- fact_tiktok_ads_daily — Daily TikTok Ads performance with website conversions
-- Aggregates ad-level data to daily totals per client.
-- Website revenue = SUM(value_per_complete_payment * complete_payment) per ad row.
{{
  config(
    materialized='incremental',
    schema='marts',
    unique_key=['client_slug', 'report_date'],
    incremental_strategy='merge',
    on_schema_change='sync_all_columns'
  )
}}

select
  client_slug,
  report_date,

  -- Spend & traffic
  coalesce(sum(spend), 0) as spend,
  sum(clicks) as clicks,
  sum(impressions) as impressions,

  -- Website conversions (TikTok Pixel)
  sum(website_purchases) as website_purchases,
  coalesce(sum(website_revenue), 0) as website_revenue,

  -- TikTok Shop / onsite
  sum(onsite_purchases) as onsite_purchases,
  coalesce(sum(onsite_revenue), 0) as onsite_revenue,

  -- Combined
  sum(total_conversions) as total_conversions,
  coalesce(sum(website_revenue), 0) + coalesce(sum(onsite_revenue), 0) as total_revenue,

  -- Calculated rates
  case when sum(clicks) > 0 then sum(spend) / sum(clicks) else 0 end as cpc,
  case when sum(impressions) > 0 then sum(spend) / sum(impressions) * 1000 else 0 end as cpm,
  case when sum(clicks) > 0 then sum(impressions)::numeric / sum(clicks) else 0 end as ctr,
  case when sum(website_purchases) > 0 then sum(spend) / sum(website_purchases) else 0 end as cost_per_purchase,
  case when sum(spend) > 0 then sum(website_revenue) / sum(spend) else 0 end as roas,

  -- Funnel
  sum(add_to_carts) as add_to_carts,
  sum(pageviews) as pageviews,

  -- Engagement
  sum(video_plays) as video_plays,
  sum(engagements) as engagements,

  -- Ad count
  count(distinct ad_id) as active_ads

from {{ ref('stg_tiktok_ads_conversions') }}
group by 1, 2
