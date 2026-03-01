-- 010_dims.sql — Dimension tables (dim_campaign, dim_geo)

-- Geography dimension (states/regions for GeoLift and geo reporting)
CREATE TABLE IF NOT EXISTS public.dim_geo (
  geo_id        TEXT PRIMARY KEY,
  geo_name      TEXT NOT NULL,
  geo_type      TEXT NOT NULL,  -- e.g. 'state', 'region', 'dma'
  country_code  TEXT NOT NULL DEFAULT 'US',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.dim_geo IS 'Geography dimension for spend/KPI by region and GeoLift holdouts.';

-- Campaign dimension (marketing campaigns for attribution and events)
CREATE TABLE IF NOT EXISTS public.dim_campaign (
  campaign_id   TEXT PRIMARY KEY,
  campaign_name TEXT,
  source        TEXT NOT NULL,  -- e.g. 'meta', 'google', 'tiktok', 'klaviyo'
  channel       TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.dim_campaign IS 'Marketing campaign dimension; links to spend and events.';
