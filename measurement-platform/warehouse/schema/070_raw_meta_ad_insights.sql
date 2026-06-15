-- 070_raw_meta_ad_insights.sql — Ad-level (creative) Meta insights landing table.
--
-- Populated by orchestration/meta_creative_sync.py (level=ad, daily). One row per
-- account per ad per day. The ad NAME carries the naming convention; it is parsed
-- downstream in dbt (stg_meta_ad_creative) into angle / hook / format dimensions,
-- so the convention can change without altering this table.
--
-- Feeds the creative-analysis section of INSIGHTS_PLAYBOOK.md (§4.3).

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.meta_ad_insights_daily (
  account_id            TEXT NOT NULL,
  campaign_id           TEXT,
  campaign_name         TEXT,
  adset_id              TEXT,
  adset_name            TEXT,
  ad_id                 TEXT NOT NULL,
  ad_name               TEXT,                  -- carries the naming convention
  date_start            DATE NOT NULL,
  date_stop             DATE,
  spend                 NUMERIC(14, 2) DEFAULT 0,
  impressions           BIGINT,
  reach                 BIGINT,
  frequency             NUMERIC(10, 4),
  clicks                BIGINT,
  inline_link_clicks    BIGINT,
  ctr                   NUMERIC(10, 4),        -- all-clicks CTR (Meta-reported)
  inline_link_click_ctr NUMERIC(10, 4),        -- link CTR (Meta-reported)
  cpc                   NUMERIC(14, 4),
  cpm                   NUMERIC(14, 4),
  video_3s_views        BIGINT,                -- hook-rate numerator (3-sec views)
  video_thruplays       BIGINT,                -- hold-rate numerator (ThruPlay)
  video_p100_views      BIGINT,                -- completed views
  video_avg_seconds     NUMERIC(10, 2),        -- avg watch time (seconds)
  actions               JSONB,                 -- add_to_cart, purchase, engagement, LPV, ...
  action_values         JSONB,                 -- omni_purchase value, ...
  synced_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (account_id, ad_id, date_start)
);

CREATE INDEX IF NOT EXISTS idx_meta_ad_insights_acct_date
  ON raw.meta_ad_insights_daily (account_id, date_start);
CREATE INDEX IF NOT EXISTS idx_meta_ad_insights_ad
  ON raw.meta_ad_insights_daily (ad_id);

COMMENT ON TABLE raw.meta_ad_insights_daily IS
  'Ad-level daily Meta insights for creative analysis (meta_creative_sync.py).';
