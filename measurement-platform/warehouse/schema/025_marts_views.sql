-- 025_marts_views.sql — Views in public schema that expose public_marts tables.
-- This allows the Supabase REST API (which only exposes the public schema)
-- to read data from dbt-materialized tables in public_marts.
--
-- Run this migration once via Supabase SQL Editor or psql:
--   psql $SUPABASE_DB_URL -f 025_marts_views.sql

-- Replace only existing views/materialized views or empty placeholder tables.
-- Fail closed for non-empty tables so this migration cannot delete live data.
do $$
declare
  target_name text;
  target regclass;
  target_kind "char";
  row_count bigint;
begin
  foreach target_name in array array['public.fact_spend_daily', 'public.fact_kpi_daily']
  loop
    target := to_regclass(target_name);
    if target is null then
      continue;
    end if;

    select relkind into target_kind from pg_class where oid = target;
    if target_kind in ('v', 'm') then
      execute format('DROP VIEW IF EXISTS %s', target);
    elsif target_kind in ('r', 'p', 'f') then
      execute format('SELECT count(*) FROM %s', target) into row_count;
      if row_count > 0 then
        raise exception 'Refusing to replace non-empty table %. Back it up and drop it manually before creating the REST view.', target;
      end if;
      execute format('DROP TABLE IF EXISTS %s', target);
    else
      raise exception 'Refusing to replace unsupported relation kind % for %', target_kind, target;
    end if;
  end loop;
end $$;

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

-- View: fact_tiktok_gmvmax_daily -> public_marts.fact_tiktok_gmv_max_daily
CREATE OR REPLACE VIEW public.fact_tiktok_gmvmax_daily AS
SELECT
    client_slug,
    report_date,
    cost AS spend,
    orders,
    gross_revenue AS revenue,
    cost_per_order,
    roas
FROM public_marts.fact_tiktok_gmv_max_daily;

COMMENT ON VIEW public.fact_tiktok_gmvmax_daily IS 'View over public_marts.fact_tiktok_gmv_max_daily for REST API access.';

-- Grant read access to the anon and authenticated roles (for REST API)
GRANT SELECT ON public.fact_spend_daily TO anon, authenticated;
GRANT SELECT ON public.fact_kpi_daily TO anon, authenticated;
GRANT SELECT ON public.fact_tiktok_gmvmax_daily TO anon, authenticated;
