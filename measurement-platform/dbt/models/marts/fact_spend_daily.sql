-- fact_spend_daily — Daily spend by channel and client.
-- Joins staging ad data with client_ad_accounts seed to assign client_slug.
-- TikTok GMV Max (Coupler.io) is added separately as channel = 'tiktok_gmvmax'.
{{
  config(
    materialized='table',
    schema='marts'
  )
}}

-- ─── Account mapping ────────────────────────────────────────────────────────────
with accounts as (
  select client_slug, platform, account_id
  from {{ ref('client_ad_accounts') }}
),

-- ─── Standard ad platforms (Meta, Google, TikTok regular) via Airbyte ───────────
meta as (
  select
    a.client_slug,
    s.report_date,
    s.channel,
    s.spend,
    s.impressions,
    s.clicks
  from {{ ref('stg_meta_spend') }} s
  inner join accounts a on a.platform = 'meta' and a.account_id = s.account_id
),

google as (
  select
    a.client_slug,
    s.report_date,
    s.channel,
    s.spend,
    s.impressions,
    s.clicks
  from {{ ref('stg_google_spend') }} s
  inner join accounts a on a.platform = 'google' and a.account_id = s.account_id
),

tiktok_regular as (
  select
    a.client_slug,
    s.report_date,
    s.channel,
    s.spend,
    s.impressions,
    s.clicks
  from {{ ref('stg_tiktok_spend') }} s
  inner join accounts a on a.platform = 'tiktok' and a.account_id = s.account_id
),

-- ─── TikTok GMV Max (Coupler.io) — separate channel for TikTok Shop campaigns ──
tiktok_gmvmax as (
  select
    'chubble' as client_slug,
    report_date,
    'tiktok_gmvmax' as channel,
    spend,
    impressions,
    clicks
  from {{ ref('stg_chubble_tiktok_gmvmax') }}
),

-- ─── Union all sources ──────────────────────────────────────────────────────────
unioned as (
  select * from meta
  union all
  select * from google
  union all
  select * from tiktok_regular
  union all
  select * from tiktok_gmvmax
)

select
  client_slug,
  report_date,
  channel,
  coalesce(sum(spend), 0) as spend,
  sum(impressions) as impressions,
  sum(clicks) as clicks
from unioned
group by 1, 2, 3
