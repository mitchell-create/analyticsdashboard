-- 020_facts.sql — Fact tables (daily spend, KPI, geo KPI, Klaviyo, TikTok organic)

-- Daily spend by channel (from Meta, Google, TikTok Ads)
CREATE TABLE IF NOT EXISTS public.fact_spend_daily (
  id            BIGSERIAL PRIMARY KEY,
  report_date   DATE NOT NULL,
  channel       TEXT NOT NULL,   -- 'meta', 'google', 'tiktok'
  spend         NUMERIC(14, 2) NOT NULL DEFAULT 0,
  impressions   BIGINT,
  clicks        BIGINT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (report_date, channel)
);

CREATE INDEX IF NOT EXISTS idx_fact_spend_daily_date ON public.fact_spend_daily (report_date);
CREATE INDEX IF NOT EXISTS idx_fact_spend_daily_channel ON public.fact_spend_daily (channel);

COMMENT ON TABLE public.fact_spend_daily IS 'Daily ad spend by channel (dbt mart).';

-- Daily KPI (revenue, orders from Shopify)
CREATE TABLE IF NOT EXISTS public.fact_kpi_daily (
  id            BIGSERIAL PRIMARY KEY,
  report_date   DATE NOT NULL,
  revenue       NUMERIC(14, 2) NOT NULL DEFAULT 0,
  orders        INT NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (report_date)
);

CREATE INDEX IF NOT EXISTS idx_fact_kpi_daily_date ON public.fact_kpi_daily (report_date);

COMMENT ON TABLE public.fact_kpi_daily IS 'Daily revenue and order count (dbt mart from Shopify).';

-- Daily KPI by geography (for GeoLift and geo reporting)
CREATE TABLE IF NOT EXISTS public.fact_kpi_geo_daily (
  id            BIGSERIAL PRIMARY KEY,
  report_date   DATE NOT NULL,
  geo_id        TEXT NOT NULL REFERENCES public.dim_geo (geo_id),
  revenue       NUMERIC(14, 2) NOT NULL DEFAULT 0,
  orders        INT NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (report_date, geo_id)
);

CREATE INDEX IF NOT EXISTS idx_fact_kpi_geo_daily_date ON public.fact_kpi_geo_daily (report_date);
CREATE INDEX IF NOT EXISTS idx_fact_kpi_geo_daily_geo ON public.fact_kpi_geo_daily (geo_id);

COMMENT ON TABLE public.fact_kpi_geo_daily IS 'Daily revenue/orders by geography (dbt mart).';

-- Daily Klaviyo campaign metrics (email/SMS blasts)
CREATE TABLE IF NOT EXISTS public.fact_klaviyo_daily (
  id            BIGSERIAL PRIMARY KEY,
  report_date   DATE NOT NULL,
  campaign_id   TEXT,
  sent          INT NOT NULL DEFAULT 0,
  opens         INT,
  clicks        INT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (report_date, campaign_id)
);

CREATE INDEX IF NOT EXISTS idx_fact_klaviyo_daily_date ON public.fact_klaviyo_daily (report_date);

COMMENT ON TABLE public.fact_klaviyo_daily IS 'Daily Klaviyo campaign metrics (dbt mart).';

-- Daily TikTok organic metrics (from Metricool)
CREATE TABLE IF NOT EXISTS public.fact_tiktok_organic_daily (
  id            BIGSERIAL PRIMARY KEY,
  report_date   DATE NOT NULL,
  views         BIGINT NOT NULL DEFAULT 0,
  likes         BIGINT,
  comments      BIGINT,
  shares        BIGINT,
  followers     BIGINT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (report_date)
);

CREATE INDEX IF NOT EXISTS idx_fact_tiktok_organic_daily_date ON public.fact_tiktok_organic_daily (report_date);

COMMENT ON TABLE public.fact_tiktok_organic_daily IS 'Daily TikTok organic metrics from Metricool (dbt mart or direct insert).';
