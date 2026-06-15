-- fact_creative_daily — Daily Meta creative performance by client.
-- From stg_meta_ad_creative joined to the client_ad_accounts seed. Counts at the
-- ad/day grain; rates (CTR, hook/hold, ATC, CPA, ROAS) are computed over SUMMED
-- counts downstream (ratio of sums, not avg of ratios). See INSIGHTS_PLAYBOOK §4.3.
--
-- Core analysis groups by creative_key (a creative + its variants) and
-- creative_type (video/image/carousel). The convention dims (angle/persona/...)
-- are carried but only populated when name_scheme = 'convention'.

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
  -- the two that drive the analysis
  c.creative_type,
  -- creative_key groups a creative's variants into one row. Default (from stg) =
  -- collapse "Copy / Copy N" duplicates. Per-client name-level rules go here:
  -- Expand pools everything from the "HOOK" marker on (text style, copy, and hook
  -- variants of the same product/audience concept) into one creative.
  case a.client_slug
    when 'expand' then btrim(regexp_replace(
      regexp_replace(c.ad_name, '(\s*[-|]\s*[^-|]*hook.*$)|(\s*[-|]\s*copy(\s+\d+)?\s*$)', '', 'i'),
      '\s+', ' ', 'g'))
    else c.creative_key
  end as creative_key,
  -- convention-only dims (dormant unless the 11-field convention is used)
  c.brand,
  c.persona,
  c.angle,
  c.style,
  c.source_tag,
  c.hook,
  c.copy_tag,
  c.offer,
  c.iteration,
  c.name_date,
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
