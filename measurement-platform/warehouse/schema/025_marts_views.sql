-- 025_marts_views.sql — Views in public schema that expose public_marts tables.
-- This allows the Supabase REST API (which only exposes the public schema)
-- to read data from dbt-materialized tables in public_marts.
--
-- Run this migration once via Supabase SQL Editor or psql:
--   psql $SUPABASE_DB_URL -f 025_marts_views.sql

-- Preserve existing public tables instead of dropping them.
-- This avoids accidental data loss when environments still write to `public`.
-- If a table exists, archive it as *_legacy and create the view at the
-- original name.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = 'fact_spend_daily'
          AND c.relkind = 'r'
    ) THEN
        IF EXISTS (
            SELECT 1
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'fact_spend_daily_legacy'
        ) THEN
            RAISE EXCEPTION 'public.fact_spend_daily exists and public.fact_spend_daily_legacy already exists; manual migration required.';
        END IF;
        ALTER TABLE public.fact_spend_daily RENAME TO fact_spend_daily_legacy;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = 'fact_kpi_daily'
          AND c.relkind = 'r'
    ) THEN
        IF EXISTS (
            SELECT 1
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'fact_kpi_daily_legacy'
        ) THEN
            RAISE EXCEPTION 'public.fact_kpi_daily exists and public.fact_kpi_daily_legacy already exists; manual migration required.';
        END IF;
        ALTER TABLE public.fact_kpi_daily RENAME TO fact_kpi_daily_legacy;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = 'fact_tiktok_gmvmax_daily'
          AND c.relkind = 'r'
    ) THEN
        IF EXISTS (
            SELECT 1
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'fact_tiktok_gmvmax_daily_legacy'
        ) THEN
            RAISE EXCEPTION 'public.fact_tiktok_gmvmax_daily exists and public.fact_tiktok_gmvmax_daily_legacy already exists; manual migration required.';
        END IF;
        ALTER TABLE public.fact_tiktok_gmvmax_daily RENAME TO fact_tiktok_gmvmax_daily_legacy;
    END IF;
END $$;

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

-- Grant read access to the anon and authenticated roles (for REST API)
GRANT SELECT ON public.fact_spend_daily TO anon, authenticated;
GRANT SELECT ON public.fact_kpi_daily TO anon, authenticated;
GRANT SELECT ON public.fact_tiktok_gmvmax_daily TO anon, authenticated;
