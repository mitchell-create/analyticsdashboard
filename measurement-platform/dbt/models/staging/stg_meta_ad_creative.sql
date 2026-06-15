-- stg_meta_ad_creative — Ad-level Meta creative staging (dual-scheme parser).
-- Source: raw.meta_ad_insights_daily (per ad per day, from meta_creative_sync.py).
--
-- Ad names come in two schemes; we parse both into the SAME dimension columns so
-- downstream analysis is scheme-agnostic:
--
--   1. CONVENTION (target, underscore-delimited, 11 fields):
--      [Brand]_[Persona]_[Angle]_[Format]_[Style]_[Source]_[Hook]_[Copy]_[Offer]_[Iteration]_[Date]
--   2. LEGACY (what's actually in the accounts, pipe-delimited + loose ` - `):
--      e.g. "Video | EXF09 - Pratico DIRECT FEMALE - Your room feels smaller HOOK - HYBRID TEXT - Copy"
--      Format is the reliable 1st field; markers (HOOK / *TEXT / FEMALE|MALE / UGC /
--      Copy N / SALE) are extracted by keyword, not position.
--
-- name_scheme records which path matched. Legacy names can't fill every field
-- (angle/brand have no reliable marker) — those stay null. One row per ad per day.
-- `copy`/`source` are suffixed _tag to avoid SQL keyword clashes.

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
    (ad_name like '%|%')                            as has_pipe,

    -- metric counts (numerators; rates computed downstream over summed counts)
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

scheme as (
  select *,
    case
      when n_underscore = 11 then 'convention'
      when has_pipe        then 'legacy_pipe'
      else 'unknown'
    end as name_scheme
  from base
),

extracted as (
  select *,
    -- ── Format (creative type): convention field 4, else 1st pipe field ──
    case
      when name_scheme = 'convention' then nullif(btrim(lower(split_part(ad_name, '_', 4))), '')
      when name_scheme = 'legacy_pipe' then nullif(btrim(lower(split_part(ad_name, '|', 1))), '')
    end as format_raw,

    -- ── Convention-only dims (positional) ──
    case when name_scheme = 'convention' then nullif(btrim(lower(split_part(ad_name, '_', 1))),  '') end as conv_brand,
    case when name_scheme = 'convention' then nullif(btrim(lower(split_part(ad_name, '_', 2))),  '') end as conv_persona,
    case when name_scheme = 'convention' then nullif(btrim(lower(split_part(ad_name, '_', 3))),  '') end as conv_angle,
    case when name_scheme = 'convention' then nullif(btrim(lower(split_part(ad_name, '_', 5))),  '') end as conv_style,
    case when name_scheme = 'convention' then nullif(btrim(lower(split_part(ad_name, '_', 6))),  '') end as conv_source,
    case when name_scheme = 'convention' then nullif(btrim(lower(split_part(ad_name, '_', 7))),  '') end as conv_hook,
    case when name_scheme = 'convention' then nullif(btrim(lower(split_part(ad_name, '_', 8))),  '') end as conv_copy,
    case when name_scheme = 'convention' then nullif(btrim(lower(split_part(ad_name, '_', 9))),  '') end as conv_offer,
    case when name_scheme = 'convention' then nullif(btrim(lower(split_part(ad_name, '_', 10))), '') end as conv_iteration,
    case when name_scheme = 'convention' then nullif(btrim(split_part(ad_name, '_', 11)),        '') end as name_date,

    -- ── Legacy keyword extraction (case-insensitive over the whole name) ──
    (lname ~ 'ugc')                                                            as is_ugc,
    case when lname ~ 'female' then 'female' when lname ~ 'male' then 'male' end as audience_gender,
    case when lname ~ 'hybrid' then 'hybrid' when lname ~ 'basic' then 'basic' end as text_style,
    (lname ~ 'hook')                                                           as has_hook_marker,
    -- hook text = the run of words just before the "HOOK" marker
    nullif(btrim(substring(lname from '([^-|]+)[[:space:]]+hook')), '')        as legacy_hook,
    -- audience descriptor, e.g. "direct female"
    nullif(btrim(concat_ws(' ',
      case when lname ~ 'direct' then 'direct' end,
      case when lname ~ 'female' then 'female' when lname ~ 'male' then 'male' end)), '') as legacy_persona,
    -- iteration: "copy" or "copy N"
    case
      when lname ~ 'copy[[:space:]]*[0-9]+' then btrim(substring(lname from 'copy[[:space:]]*[0-9]+'))
      when lname ~ 'copy'                   then 'copy'
    end as legacy_iteration,
    -- offer: "<word> sale" / "NN% off"
    nullif(btrim(substring(lname from '([0-9]+%[[:space:]]*off|[a-z]+[[:space:]]+sale|sale)')), '') as legacy_offer
  from scheme
)

select
  account_id, ad_id, ad_name, adset_name, campaign_name, report_date,
  name_scheme,
  (name_scheme = 'convention') as parse_ok,
  n_underscore,

  -- canonical format (works for BOTH schemes); format_raw keeps the original token
  case
    when format_raw ~ 'vid'                    then 'video'
    when format_raw ~ 'carous'                 then 'carousel'
    when format_raw ~ 'ugc'                    then 'ugc'
    when format_raw ~ 'img|image|static|stat'  then 'image'
    when format_raw ~ 'gif'                    then 'gif'
    else format_raw
  end as format,
  format_raw,

  -- unified dims: convention value first, else legacy best-effort
  conv_brand                                           as brand,
  coalesce(conv_persona, legacy_persona)               as persona,
  conv_angle                                           as angle,
  coalesce(conv_style, text_style,
           case when is_ugc then 'ugc' end)            as style,
  conv_source                                          as source_tag,
  coalesce(conv_hook, legacy_hook)                     as hook,
  conv_copy                                            as copy_tag,
  coalesce(conv_offer, legacy_offer)                   as offer,
  coalesce(conv_iteration, legacy_iteration)           as iteration,
  name_date,

  -- raw legacy flags (handy for filtering even when a unified dim is null)
  is_ugc,
  audience_gender,
  text_style,
  has_hook_marker,

  -- metric counts
  spend, impressions, reach, frequency, link_clicks, clicks,
  video_3s_views, video_thruplays, video_p100_views, video_avg_seconds,
  add_to_cart, landing_page_views, post_engagement, purchases, conversion_value
from extracted
