-- fact_creative_daily — Daily Meta creative performance by client + parsed creative
-- dimensions. From stg_meta_ad_creative joined to the client_ad_accounts seed.
--
-- Counts are stored at the ad/day grain; compute rates (link CTR, hook/hold, ATC,
-- CPA, ROAS) over SUMMED counts at query time (ratio of sums, not avg of ratios).
-- See INSIGHTS_PLAYBOOK.md §4.3.

{{ config(materialized='table', schema='marts') }}

with creative as (
  select * from {{ ref('stg_meta_ad_creative') }}
),

accounts as (
  select client_slug, account_id
  from {{ ref('client_ad_accounts') }}
  where platform = 'meta'
)

select
  a.client_slug,
  c.report_date,
  c.ad_id,
  c.ad_name,
  c.adset_name,
  c.campaign_name,
  c.name_scheme,
  c.parse_ok,
  -- parsed creative dimensions (unified across both naming schemes)
  c.brand,
  c.persona,
  c.angle,
  c.format,
  c.format_raw,
  c.style,
  c.source_tag,
  c.hook,
  c.copy_tag,
  c.offer,
  c.iteration,
  c.name_date,
  -- legacy keyword flags (populated even when a unified dim is null)
  c.is_ugc,
  c.audience_gender,
  c.text_style,
  c.has_hook_marker,
  -- metric counts
  c.spend,
  c.impressions,
  c.reach,
  c.frequency,
  c.link_clicks,
  c.clicks,
  c.video_3s_views,
  c.video_thruplays,
  c.video_p100_views,
  c.video_avg_seconds,
  c.add_to_cart,
  c.landing_page_views,
  c.post_engagement,
  c.purchases,
  c.conversion_value
from creative c
inner join accounts a on a.account_id = c.account_id
