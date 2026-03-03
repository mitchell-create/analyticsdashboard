-- 065_multi_tenant.sql — Migrate to shared-DB multi-tenant model
-- Adds client_slug to all per-client tables so one Supabase project serves all clients.
-- Run AFTER 000-060 migrations. Safe to re-run (IF NOT EXISTS / IF NOT).
--
-- After running, set a default client_slug for existing data:
--   UPDATE fact_spend_daily SET client_slug = 'your-first-client' WHERE client_slug = 'default';
--   (repeat for each table)

-- ============================================================
-- Fact tables: add client_slug + update unique constraints
-- ============================================================

-- fact_spend_daily
ALTER TABLE public.fact_spend_daily
  ADD COLUMN IF NOT EXISTS client_slug TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.fact_spend_daily
  DROP CONSTRAINT IF EXISTS fact_spend_daily_report_date_channel_key;
ALTER TABLE public.fact_spend_daily
  ADD CONSTRAINT fact_spend_daily_client_date_channel_key
  UNIQUE (client_slug, report_date, channel);
CREATE INDEX IF NOT EXISTS idx_fact_spend_daily_client
  ON public.fact_spend_daily (client_slug);

-- fact_kpi_daily
ALTER TABLE public.fact_kpi_daily
  ADD COLUMN IF NOT EXISTS client_slug TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.fact_kpi_daily
  DROP CONSTRAINT IF EXISTS fact_kpi_daily_report_date_key;
ALTER TABLE public.fact_kpi_daily
  ADD CONSTRAINT fact_kpi_daily_client_date_key
  UNIQUE (client_slug, report_date);
CREATE INDEX IF NOT EXISTS idx_fact_kpi_daily_client
  ON public.fact_kpi_daily (client_slug);

-- fact_kpi_geo_daily
ALTER TABLE public.fact_kpi_geo_daily
  ADD COLUMN IF NOT EXISTS client_slug TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.fact_kpi_geo_daily
  DROP CONSTRAINT IF EXISTS fact_kpi_geo_daily_report_date_geo_id_key;
ALTER TABLE public.fact_kpi_geo_daily
  ADD CONSTRAINT fact_kpi_geo_daily_client_date_geo_key
  UNIQUE (client_slug, report_date, geo_id);
CREATE INDEX IF NOT EXISTS idx_fact_kpi_geo_daily_client
  ON public.fact_kpi_geo_daily (client_slug);

-- fact_klaviyo_daily
ALTER TABLE public.fact_klaviyo_daily
  ADD COLUMN IF NOT EXISTS client_slug TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.fact_klaviyo_daily
  DROP CONSTRAINT IF EXISTS fact_klaviyo_daily_report_date_campaign_id_key;
ALTER TABLE public.fact_klaviyo_daily
  ADD CONSTRAINT fact_klaviyo_daily_client_date_campaign_key
  UNIQUE (client_slug, report_date, campaign_id);
CREATE INDEX IF NOT EXISTS idx_fact_klaviyo_daily_client
  ON public.fact_klaviyo_daily (client_slug);

-- fact_tiktok_organic_daily
ALTER TABLE public.fact_tiktok_organic_daily
  ADD COLUMN IF NOT EXISTS client_slug TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.fact_tiktok_organic_daily
  DROP CONSTRAINT IF EXISTS fact_tiktok_organic_daily_report_date_key;
ALTER TABLE public.fact_tiktok_organic_daily
  ADD CONSTRAINT fact_tiktok_organic_daily_client_date_key
  UNIQUE (client_slug, report_date);
CREATE INDEX IF NOT EXISTS idx_fact_tiktok_organic_daily_client
  ON public.fact_tiktok_organic_daily (client_slug);

-- ============================================================
-- Event / experiment / operational tables
-- ============================================================

-- marketing_events
ALTER TABLE public.marketing_events
  ADD COLUMN IF NOT EXISTS client_slug TEXT NOT NULL DEFAULT 'default';
CREATE INDEX IF NOT EXISTS idx_marketing_events_client
  ON public.marketing_events (client_slug);

-- experiments
ALTER TABLE public.experiments
  ADD COLUMN IF NOT EXISTS client_slug TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.experiments
  DROP CONSTRAINT IF EXISTS experiments_experiment_slug_key;
ALTER TABLE public.experiments
  ADD CONSTRAINT experiments_client_slug_key
  UNIQUE (client_slug, experiment_slug);
CREATE INDEX IF NOT EXISTS idx_experiments_client
  ON public.experiments (client_slug);

-- dim_campaign (per-client)
ALTER TABLE public.dim_campaign
  ADD COLUMN IF NOT EXISTS client_slug TEXT NOT NULL DEFAULT 'default';
ALTER TABLE public.dim_campaign
  DROP CONSTRAINT IF EXISTS dim_campaign_pkey;
ALTER TABLE public.dim_campaign
  ADD CONSTRAINT dim_campaign_client_pkey
  PRIMARY KEY (client_slug, campaign_id);

-- data_quality_flags
ALTER TABLE public.data_quality_flags
  ADD COLUMN IF NOT EXISTS client_slug TEXT NOT NULL DEFAULT 'default';
CREATE INDEX IF NOT EXISTS idx_data_quality_flags_client
  ON public.data_quality_flags (client_slug);

-- pipeline_runs
ALTER TABLE public.pipeline_runs
  ADD COLUMN IF NOT EXISTS client_slug TEXT NOT NULL DEFAULT 'default';
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_client
  ON public.pipeline_runs (client_slug);

-- ai_query_audit
ALTER TABLE public.ai_query_audit
  ADD COLUMN IF NOT EXISTS client_slug TEXT;
CREATE INDEX IF NOT EXISTS idx_ai_query_audit_client
  ON public.ai_query_audit (client_slug);

-- ============================================================
-- Note: dim_geo and experiment_results are NOT per-client.
--   dim_geo: shared reference data (US states are the same for all).
--   experiment_results: linked to experiments via experiment_id (which has client_slug).
-- ============================================================
