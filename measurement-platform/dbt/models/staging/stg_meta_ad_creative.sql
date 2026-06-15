-- stg_meta_ad_creative — Ad-level Meta creative staging.
-- Source: raw.meta_ad_insights_daily (per ad per day, from meta_creative_sync.py).
-- Parses the ad NAME into the agency naming convention and extracts conversion
-- counts from the actions / action_values jsonb. One row per ad per day.
--
-- Naming convention (underscore-delimited, 11 fields):
--   [Brand]_[Persona]_[Angle]_[Format]_[Style]_[Source]_[Hook]_[Copy]_[Offer]_[Iteration]_[Date]
--
-- Names that don't split into 11 fields are KEPT (metrics still count) but flagged
-- parse_ok = false, so coverage is visible — never silently dropped. `copy` and
-- `source` are suffixed _tag to avoid SQL keyword clashes.

{{ config(materialized='view', schema='staging') }}

with source as (
  select * from {{ source('raw_airbyte', 'meta_ad_insights_daily') }}
),

parsed as (
  select
    account_id::text                                as account_id,
    ad_id::text                                     as ad_id,
    ad_name,
    adset_name,
    campaign_name,
    date_start::date                                as report_date,
    array_length(string_to_array(ad_name, '_'), 1)  as n_parts,

    -- Positional parse (1-indexed); lower + trim for clean grouping.
    nullif(btrim(lower(split_part(ad_name, '_', 1))),  '') as brand,
    nullif(btrim(lower(split_part(ad_name, '_', 2))),  '') as persona,
    nullif(btrim(lower(split_part(ad_name, '_', 3))),  '') as angle,
    nullif(btrim(lower(split_part(ad_name, '_', 4))),  '') as format_raw,
    nullif(btrim(lower(split_part(ad_name, '_', 5))),  '') as style,
    nullif(btrim(lower(split_part(ad_name, '_', 6))),  '') as source_tag,
    nullif(btrim(lower(split_part(ad_name, '_', 7))),  '') as hook,
    nullif(btrim(lower(split_part(ad_name, '_', 8))),  '') as copy_tag,
    nullif(btrim(lower(split_part(ad_name, '_', 9))),  '') as offer,
    nullif(btrim(lower(split_part(ad_name, '_', 10))), '') as iteration,
    nullif(btrim(split_part(ad_name, '_', 11)),        '') as name_date,

    -- Metric COUNTS (numerators). Rates are computed at query time over summed
    -- counts (ratio of sums), never averaged per-row.
    coalesce(spend, 0)            as spend,
    impressions,
    reach,
    frequency,
    inline_link_clicks           as link_clicks,
    clicks,
    video_3s_views,
    video_thruplays,
    video_p100_views,
    video_avg_seconds,
    coalesce((select sum((a->>'value')::numeric) from jsonb_array_elements(coalesce(actions, '[]'::jsonb)) a
              where a->>'action_type' = 'omni_add_to_cart'), 0)   as add_to_cart,
    coalesce((select sum((a->>'value')::numeric) from jsonb_array_elements(coalesce(actions, '[]'::jsonb)) a
              where a->>'action_type' = 'landing_page_view'), 0)  as landing_page_views,
    coalesce((select sum((a->>'value')::numeric) from jsonb_array_elements(coalesce(actions, '[]'::jsonb)) a
              where a->>'action_type' = 'post_engagement'), 0)    as post_engagement,
    coalesce((select sum((a->>'value')::numeric) from jsonb_array_elements(coalesce(actions, '[]'::jsonb)) a
              where a->>'action_type' = 'omni_purchase'), 0)      as purchases,
    coalesce((select sum((v->>'value')::numeric) from jsonb_array_elements(coalesce(action_values, '[]'::jsonb)) v
              where v->>'action_type' = 'omni_purchase'), 0)      as conversion_value
  from source
)

select
  *,
  (n_parts = 11) as parse_ok,
  -- Best-effort canonical format from the [Format] token; tune once real tokens
  -- are seen (format_raw is retained for inspection).
  case
    when format_raw like '%vid%'                               then 'video'
    when format_raw like '%ugc%'                               then 'ugc'
    when format_raw like '%carous%'                            then 'carousel'
    when format_raw like '%gif%'                               then 'gif'
    when format_raw like '%img%' or format_raw like '%image%'
      or format_raw like '%stat%'                              then 'image'
    else format_raw
  end as format
from parsed
