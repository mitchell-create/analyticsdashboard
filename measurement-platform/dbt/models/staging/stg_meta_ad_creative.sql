-- stg_meta_ad_creative — Ad-level Meta creative staging.
-- Source: raw.meta_ad_insights_daily (per ad per day, from meta_creative_sync.py).
--
-- Philosophy: don't DECODE the meaning of an ad name (angle/persona/etc.) — names
-- are too inconsistent across clients for that to be reliable. Instead:
--   * creative_type — video / image / carousel (keyword scan; works on any name)
--   * creative_key  — the ad name as a grouping fingerprint, with trailing
--                     "Copy / Copy N" iteration suffixes stripped so a creative's
--                     variants collapse into ONE row. We rank these by the metric
--                     panel downstream (playbook §4.3) and read each winner's
--                     weakest funnel stage as its iteration lever.
--
-- The 11-field underscore convention is still parsed when present (name_scheme =
-- 'convention') so angle/persona/hook light up automatically IF a client adopts
-- it — but those dims are NOT required for the core "which creative wins" read.
--
-- One row per ad per day. `copy`/`source` are suffixed _tag to dodge SQL keywords.

{{ config(materialized='view', schema='staging') }}

with source as (
  select * from {{ source('raw_airbyte', 'meta_ad_insights_daily') }}
),

base as (
  select
    account_id::text                                as account_id,
    ad_id::text                                     as ad_id,
    ad_name,
    lower(ad_name)                                  as lname,
    adset_name,
    campaign_name,
    date_start::date                                as report_date,
    array_length(string_to_array(ad_name, '_'), 1)  as n_underscore,

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
),

tagged as (
  select *,
    (n_underscore = 11) as is_convention,

    -- creative_type: keyword first, then convention field 4, then first token
    coalesce(
      case
        when lname ~ 'carousel'      then 'carousel'
        when lname ~ 'video'         then 'video'
        when lname ~ 'image|static'  then 'image'
        when lname ~ 'gif'           then 'gif'
      end,
      case when n_underscore = 11 then nullif(btrim(lower(split_part(ad_name, '_', 4))), '') end,
      nullif(btrim(lower(regexp_replace(ad_name, '[|_].*$', ''))), '')
    ) as creative_type,

    -- creative_key: ad name minus a trailing "Copy / Copy N", whitespace collapsed.
    -- One creative's variants share a key, so they group into a single row.
    btrim(regexp_replace(
      regexp_replace(ad_name, '[[:space:]]*[-|][[:space:]]*[Cc]opy([[:space:]]+[0-9]+)?[[:space:]]*$', ''),
      '[[:space:]]+', ' ', 'g')) as creative_key
  from base
)

select
  account_id, ad_id, ad_name, adset_name, campaign_name, report_date,
  case when is_convention then 'convention' else 'name' end as name_scheme,
  is_convention as parse_ok,
  creative_type,
  creative_key,

  -- Convention-only dims (dormant unless the 11-field convention is used).
  case when is_convention then nullif(btrim(lower(split_part(ad_name, '_', 1))),  '') end as brand,
  case when is_convention then nullif(btrim(lower(split_part(ad_name, '_', 2))),  '') end as persona,
  case when is_convention then nullif(btrim(lower(split_part(ad_name, '_', 3))),  '') end as angle,
  case when is_convention then nullif(btrim(lower(split_part(ad_name, '_', 5))),  '') end as style,
  case when is_convention then nullif(btrim(lower(split_part(ad_name, '_', 6))),  '') end as source_tag,
  case when is_convention then nullif(btrim(lower(split_part(ad_name, '_', 7))),  '') end as hook,
  case when is_convention then nullif(btrim(lower(split_part(ad_name, '_', 8))),  '') end as copy_tag,
  case when is_convention then nullif(btrim(lower(split_part(ad_name, '_', 9))),  '') end as offer,
  case when is_convention then nullif(btrim(lower(split_part(ad_name, '_', 10))), '') end as iteration,
  case when is_convention then nullif(btrim(split_part(ad_name, '_', 11)),        '') end as name_date,

  spend, impressions, reach, frequency, link_clicks, clicks,
  video_3s_views, video_thruplays, video_p100_views, video_avg_seconds,
  add_to_cart, landing_page_views, post_engagement, purchases, conversion_value
from tagged
