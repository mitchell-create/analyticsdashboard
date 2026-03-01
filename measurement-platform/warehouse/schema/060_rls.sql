-- 060_rls.sql — Enable Row Level Security on all public tables
-- Run after Supabase is healthy. Addresses security advisor warnings.
-- service_role bypasses RLS; anon/authenticated have no access without policies (backend-only warehouse).

-- Enable RLS on all warehouse and dbt tables
ALTER TABLE IF EXISTS public.client_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.dim_geo ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.dim_campaign ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.fact_spend_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.fact_kpi_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.fact_kpi_geo_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.fact_klaviyo_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.fact_tiktok_organic_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.marketing_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.experiments ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.experiment_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.data_quality_flags ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.ai_query_audit ENABLE ROW LEVEL SECURITY;

-- dbt seed (may be in public or public_marts)
ALTER TABLE IF EXISTS public.dim_geo_states ENABLE ROW LEVEL SECURITY;

-- dbt marts (tables in public_marts schema)
ALTER TABLE IF EXISTS public_marts.dim_geo ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public_marts.dim_campaign ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public_marts.fact_spend_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public_marts.fact_kpi_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public_marts.fact_kpi_geo_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public_marts.fact_klaviyo_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public_marts.fact_tiktok_organic_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public_marts.dim_geo_states ENABLE ROW LEVEL SECURITY;
