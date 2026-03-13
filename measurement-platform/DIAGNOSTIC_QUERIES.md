# Diagnostic Queries — Expand Report Data Verification

Run these queries in your Supabase SQL Editor (Expand client database) to verify the data feeding into Slack reports. Use them to debug incorrect revenue, orders, or ad spend.

## 1. Orders & Revenue — February 2026 vs January 2026

```sql
-- Total orders and revenue by calendar month
SELECT
  date_trunc('month', report_date)::date AS month_start,
  SUM(orders) AS total_orders,
  SUM(revenue) AS total_revenue,
  ROUND(SUM(revenue) / NULLIF(SUM(orders), 0), 2) AS aov
FROM public_marts.fact_kpi_daily
WHERE report_date >= '2026-01-01' AND report_date <= '2026-02-29'
  -- Add "AND client_slug = 'expand'" if your fact_kpi_daily has that column
GROUP BY 1
ORDER BY 1;
```

**What to check:**
- February 2026 should show ~200 orders (per your expectation), not ~3,000
- Revenue for Feb should be ~$564,000
- If orders are 15x too high: possible duplicate rows in raw `expand_orders`, or wrong aggregation (e.g. line items vs orders)

## 2. Raw Shopify Orders — Row Count Check

```sql
-- Count raw order rows in Feb 2026 (detect duplicates)
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT id) AS distinct_order_ids
FROM raw.expand_orders
WHERE created_at::date >= '2026-02-01' AND created_at::date <= '2026-02-29'
  AND financial_status NOT IN ('refunded', 'voided');
```

**What to check:**
- If `row_count` >> `distinct_order_ids`, you have duplicates
- If `row_count` is ~3,000 but you expect ~200 orders, raw data may include multiple stores or wrong filters

## 3. Ad Spend by Channel — February 2026

```sql
-- Total spend by channel for Feb 2026
SELECT
  channel,
  SUM(spend) AS total_spend,
  SUM(impressions) AS impressions,
  SUM(clicks) AS clicks
FROM public_marts.fact_spend_daily
WHERE report_date >= '2026-02-01' AND report_date <= '2026-02-29'
  -- Add "AND client_slug = 'expand'" if your fact_spend_daily has that column
GROUP BY channel
ORDER BY total_spend DESC;
```

**What to check:**
- Total ad spend should be ~$30,000–$40,000 for Feb, not ~$65,000
- If 2x too high: wrong period (e.g. 60 days summed), duplicate raw data, or multi-account aggregation

## 4. Rolling vs Calendar Period Comparison

The Slack report previously used **rolling windows** (e.g. "past 30 days vs previous 30 days") instead of **calendar months**. Example:

- Run on March 13: "past 30 days" = Feb 11 – Mar 12, "previous 30 days" = Jan 12 – Feb 10  
- That is **not** February vs January.

**Fix applied:** When you say "February 2026 vs January 2026" or "diagnostic report February vs January", the bot now uses calendar dates:
- Current: Feb 1 – Feb 28
- Prior: Jan 1 – Jan 31

## 5. Table Structure — Does `client_slug` Exist?

```sql
-- Check if fact tables have client_slug
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public_marts'
  AND table_name IN ('fact_kpi_daily', 'fact_spend_daily')
  AND column_name = 'client_slug';
```

If `client_slug` exists, ensure queries filter by `client_slug = 'expand'` when you have multiple clients in the same DB.

---

## Quick Checklist

| Issue | Likely Cause | Action |
|-------|--------------|--------|
| Orders ~3,000 instead of ~200 | Duplicates in raw, wrong table, or wrong period | Run query #2, check `expand_orders` for duplicates |
| Ad spend ~$65k instead of ~$30–40k | Rolling 60-day sum, duplicates, or multi-account | Run query #3, verify date range and channel breakdown |
| Revenue numbers swapped (Jan/Feb reversed) | Rolling period misaligned with calendar months | Use "February 2026 vs January 2026" explicitly; bot now uses calendar months |
| Google/Meta metrics wrong | Same period/spend issues | Fix overall period first; channel metrics inherit from same sources |
