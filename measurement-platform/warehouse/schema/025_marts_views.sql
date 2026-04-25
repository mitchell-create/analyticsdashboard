-- 025_marts_views.sql — Views in public schema that expose public_marts tables.
-- This allows the Supabase REST API (which only exposes the public schema)
-- to read data from dbt-materialized tables in public_marts.
--
-- Run this migration once via Supabase SQL Editor or psql:
--   psql $SUPABASE_DB_URL -f 025_marts_views.sql

-- Drop existing empty shell tables so we can replace them with views.
-- (The original 020_facts.sql created empty tables in public schema;
--  dbt writes the actual data to public_marts.)
DO $$
DECLARE
    relation_kind "char";
    rows_found boolean;
BEGIN
    SELECT c.relkind INTO relation_kind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'fact_spend_daily';

    IF relation_kind IN ('r', 'p', 'f') THEN
        EXECUTE 'SELECT EXISTS (SELECT 1 FROM public.fact_spend_daily LIMIT 1)' INTO rows_found;
        IF rows_found THEN
            RAISE EXCEPTION 'Refusing to replace non-empty public.fact_spend_daily';
        END IF;
        DROP TABLE public.fact_spend_daily CASCADE;
    ELSIF relation_kind IS NOT NULL AND relation_kind <> 'v' THEN
        RAISE EXCEPTION 'Refusing to replace unsupported relation public.fact_spend_daily (relkind=%)', relation_kind;
    END IF;

    SELECT c.relkind INTO relation_kind
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'fact_kpi_daily';

    IF relation_kind IN ('r', 'p', 'f') THEN
        EXECUTE 'SELECT EXISTS (SELECT 1 FROM public.fact_kpi_daily LIMIT 1)' INTO rows_found;
        IF rows_found THEN
            RAISE EXCEPTION 'Refusing to replace non-empty public.fact_kpi_daily';
        END IF;
        DROP TABLE public.fact_kpi_daily CASCADE;
    ELSIF relation_kind IS NOT NULL AND relation_kind <> 'v' THEN
        RAISE EXCEPTION 'Refusing to replace unsupported relation public.fact_kpi_daily (relkind=%)', relation_kind;
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
