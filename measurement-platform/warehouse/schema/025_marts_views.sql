-- 025_marts_views.sql — Views in public schema that expose public_marts tables.
-- This allows the Supabase REST API (which only exposes the public schema)
-- to read data from dbt-materialized tables in public_marts.
--
-- Run this migration once via Supabase SQL Editor or psql:
--   psql $SUPABASE_DB_URL -f 025_marts_views.sql

-- Drop existing empty table placeholders so we can replace them with views.
-- (The original 020_facts.sql created empty tables in public schema;
--  dbt writes the actual data to public_marts.)
DO $$
DECLARE
    existing_kind "char";
    existing_rows bigint;
BEGIN
    SELECT c.relkind INTO existing_kind
    FROM pg_class c
    WHERE c.oid = to_regclass('public.fact_spend_daily');

    IF existing_kind IN ('r', 'p', 'f') THEN
        EXECUTE 'SELECT count(*) FROM public.fact_spend_daily' INTO existing_rows;
        IF existing_rows > 0 THEN
            RAISE EXCEPTION 'Refusing to replace non-empty table public.fact_spend_daily with a view';
        END IF;
        DROP TABLE public.fact_spend_daily;
    ELSIF existing_kind = 'm' THEN
        DROP MATERIALIZED VIEW public.fact_spend_daily;
    END IF;
END $$;

DO $$
DECLARE
    existing_kind "char";
    existing_rows bigint;
BEGIN
    SELECT c.relkind INTO existing_kind
    FROM pg_class c
    WHERE c.oid = to_regclass('public.fact_kpi_daily');

    IF existing_kind IN ('r', 'p', 'f') THEN
        EXECUTE 'SELECT count(*) FROM public.fact_kpi_daily' INTO existing_rows;
        IF existing_rows > 0 THEN
            RAISE EXCEPTION 'Refusing to replace non-empty table public.fact_kpi_daily with a view';
        END IF;
        DROP TABLE public.fact_kpi_daily;
    ELSIF existing_kind = 'm' THEN
        DROP MATERIALIZED VIEW public.fact_kpi_daily;
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
