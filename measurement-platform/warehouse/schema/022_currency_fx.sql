-- 022_currency_fx.sql — Currency conversion config and FX-adjusted spend view
-- Supports multi-currency clients where ad platform currency differs from Shopify currency.
-- Run on each client DB after 020_facts.sql.

-- Per-client currency configuration for ad platform → Shopify conversion
CREATE TABLE IF NOT EXISTS public_marts.currency_config (
  client_slug           TEXT PRIMARY KEY,
  shopify_currency      TEXT NOT NULL DEFAULT 'USD',
  ad_platform_currency  TEXT NOT NULL DEFAULT 'USD',
  ad_to_shopify_rate    NUMERIC NOT NULL DEFAULT 1.0,
  notes                 TEXT
);

COMMENT ON TABLE public_marts.currency_config IS
  'Maps each client''s ad platform currency to their Shopify currency with a conversion rate. '
  'Rate is ad_platform_currency → shopify_currency (e.g. 1 CAD → 0.72 USD). '
  'Clients not in this table default to rate=1.0 (no conversion).';

-- FX-adjusted daily spend view
-- Wraps fact_spend_daily and multiplies spend by the conversion rate.
-- Impressions and clicks pass through unchanged (not currency-denominated).
-- If a client has no entry in currency_config, rate defaults to 1.0.
CREATE OR REPLACE VIEW public_marts.fact_spend_daily_fx AS
SELECT
  f.client_slug,
  f.report_date,
  f.channel,
  f.spend * COALESCE(c.ad_to_shopify_rate, 1.0) AS spend,
  f.impressions,
  f.clicks
FROM public_marts.fact_spend_daily f
LEFT JOIN public_marts.currency_config c ON f.client_slug = c.client_slug;

COMMENT ON VIEW public_marts.fact_spend_daily_fx IS
  'fact_spend_daily with ad spend converted to Shopify currency via currency_config rate. '
  'Drop-in replacement for fact_spend_daily in any query that reports spend in Shopify currency.';
