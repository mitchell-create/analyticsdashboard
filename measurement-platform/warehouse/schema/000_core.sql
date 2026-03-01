-- 000_core.sql — Client/config and core schema setup (Pattern B: 1 DB per client)
-- Run first when provisioning a new client warehouse.

-- Optional: client config table for multi-tenant metadata (e.g. timezone, currency)
CREATE TABLE IF NOT EXISTS public.client_config (
  id            SERIAL PRIMARY KEY,
  client_slug   TEXT NOT NULL UNIQUE,
  timezone      TEXT NOT NULL DEFAULT 'America/New_York',
  currency      TEXT NOT NULL DEFAULT 'USD',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ensure public schema exists and is default for this migration set
COMMENT ON TABLE public.client_config IS 'Per-client configuration (timezone, currency). One row per client in Pattern B.';
