-- fact_tiktok_ads_daily — Daily TikTok Ads WEBSITE performance
-- Website conversions only (TikTok Pixel). Does NOT include TikTok Shop.
-- For TikTok Shop data, see fact_tiktok_gmv_max_daily (coupler.io pipeline).
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

  -- Website conversions (TikTok Pixel only — NOT TikTok Shop)
  sum(website_purchases) as website_purchases,
  coalesce(sum(website_revenue), 0) as website_revenue,

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
