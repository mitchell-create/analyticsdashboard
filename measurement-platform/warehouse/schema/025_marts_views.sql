-- 025_marts_views.sql — Views in public schema that expose public_marts tables.
-- This allows the Supabase REST API (which only exposes the public schema)
-- to read data from dbt-materialized tables in public_marts.
--
-- Run this migration once via Supabase SQL Editor or psql:
--   psql $SUPABASE_DB_URL -f 025_marts_views.sql

-- Drop existing empty tables so we can replace them with views.
-- (The original 020_facts.sql created empty tables in public schema;
--  dbt writes the actual data to public_marts.)
DROP TABLE IF EXISTS public.fact_spend_daily CASCADE;
DROP TABLE IF EXISTS public.fact_kpi_daily CASCADE;

-- View: fact_spend_daily -> public_marts.fact_spend_daily
CREATE OR REPLACE VIEW public.fact_spend_daily AS
SELECT
    client_slug,
    report_date,
    channel,
    spend,
    impressions,
    clicks
FROM public_marts.fact_spend_daily;

COMMENT ON VIEW public.fact_spend_daily IS 'View over public_marts.fact_spend_daily for REST API access.';

-- View: fact_kpi_daily -> public_marts.fact_kpi_daily
CREATE OR REPLACE VIEW public.fact_kpi_daily AS
SELECT
    client_slug,
    report_date,
    revenue,
    orders
FROM public_marts.fact_kpi_daily;

COMMENT ON VIEW public.fact_kpi_daily IS 'View over public_marts.fact_kpi_daily for REST API access.';

-- View: fact_tiktok_gmvmax_daily -> public_marts.fact_tiktok_gmvmax_daily
CREATE OR REPLACE VIEW public.fact_tiktok_gmvmax_daily AS
SELECT
    client_slug,
    report_date,
    spend,
    orders,
    revenue,
    cost_per_order,
    roas
FROM public_marts.fact_tiktok_gmvmax_daily;

COMMENT ON VIEW public.fact_tiktok_gmvmax_daily IS 'View over public_marts.fact_tiktok_gmvmax_daily for REST API access.';

-- Restrict view access to service_role only to avoid exposing cross-client metrics.
REVOKE ALL ON public.fact_spend_daily FROM anon, authenticated;
REVOKE ALL ON public.fact_kpi_daily FROM anon, authenticated;
REVOKE ALL ON public.fact_tiktok_gmvmax_daily FROM anon, authenticated;
GRANT SELECT ON public.fact_spend_daily TO service_role;
GRANT SELECT ON public.fact_kpi_daily TO service_role;
GRANT SELECT ON public.fact_tiktok_gmvmax_daily TO service_role;
