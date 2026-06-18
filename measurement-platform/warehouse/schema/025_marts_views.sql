-- 025_marts_views.sql — Views in public schema that expose public_marts tables.
-- This allows the Supabase REST API (which only exposes the public schema)
-- to read data from dbt-materialized tables in public_marts.
--
-- Run this migration once via Supabase SQL Editor or psql:
--   psql $SUPABASE_DB_URL -f 025_marts_views.sql

-- Safety: only drop legacy public tables when they are empty.
-- If any of these tables contain rows, abort to avoid data loss.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'fact_spend_daily'
    ) THEN
        IF EXISTS (SELECT 1 FROM public.fact_spend_daily LIMIT 1) THEN
            RAISE EXCEPTION
                'Refusing to drop public.fact_spend_daily because it contains data. Migrate data before running 025_marts_views.sql.';
        END IF;
        DROP TABLE public.fact_spend_daily CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'fact_kpi_daily'
    ) THEN
        IF EXISTS (SELECT 1 FROM public.fact_kpi_daily LIMIT 1) THEN
            RAISE EXCEPTION
                'Refusing to drop public.fact_kpi_daily because it contains data. Migrate data before running 025_marts_views.sql.';
        END IF;
        DROP TABLE public.fact_kpi_daily CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'fact_tiktok_gmvmax_daily'
    ) THEN
        IF EXISTS (SELECT 1 FROM public.fact_tiktok_gmvmax_daily LIMIT 1) THEN
            RAISE EXCEPTION
                'Refusing to drop public.fact_tiktok_gmvmax_daily because it contains data. Migrate data before running 025_marts_views.sql.';
        END IF;
        DROP TABLE public.fact_tiktok_gmvmax_daily CASCADE;
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
