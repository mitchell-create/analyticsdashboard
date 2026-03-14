# Dashboard Roadmap — Future Tasks & Enhancements
# Last updated: 2026-03-12
# Dashboard: 131 (Client Performance Template v2) — 95 dashcards

---

## 1. Google Analytics Integration
**Status:** BLOCKED — waiting for GA4 to be connected via Airbyte
**Details:** See GOOGLE_ANALYTICS_TASKS.md for full breakdown

### When GA is connected:
- [ ] Create staging model `stg_ga_sessions.sql` (daily sessions, source/medium, new vs returning)
- [ ] Create mart model `fact_ga_daily.sql` (aggregated daily metrics)
- [ ] **Website CVR** card (Orders / Sessions) — add to Executive KPIs alongside Paid CVR
- [ ] **Cost Per Session** card (Total Ad Spend / Sessions)
- [ ] **Full Website Funnel** (Sessions → Product Views → ATC → Checkout → Purchase)
  - Replace current 2-stage Total Funnel (Clicks → Orders)
  - Add stage conversion rates between each step
- [ ] **Cart Abandonment Rate** (1 - Checkouts / ATCs)
- [ ] **Checkout Abandonment Rate** (1 - Purchases / Checkouts)
- [ ] **Website CVR vs Paid CVR** comparison line chart (daily + 7-day rolling avg)
- [ ] **Sessions by Source/Medium** (Organic vs Paid vs Direct vs Referral vs Email, stacked area)
- [ ] **Bounce Rate by Channel** (table or bar — assess landing page quality)
- [ ] **New vs Returning Visitors** (pairs with existing Shopify customer metrics)
- [ ] **Revenue Per Session** trend line
- [ ] **Pages Per Session** (engagement depth)
- [ ] **Landing Page Performance** (top pages by CVR, bounce rate)
- [ ] Update Stage Conversion Rates table with session-based rates
- [ ] Update glossary text card with Website CVR definition

---

## 2. Google Ads Attribution Window ROAS
**Status:** BLOCKED — requires additional Airbyte report stream
**Why:** Expand has a very long purchase window; comparing ROAS at different attribution
windows (1d click, 7d click, 28d click) vs standard ROAS reveals true campaign value.

### What's needed:
- [ ] Configure Airbyte to sync `conversion_by_conversion_date` or `conversion_lag_bucket` report from Google Ads API
- [ ] No `conversion_lag_bucket`, `attribution`, or `window` columns exist in current `raw.account_performance_report`
- [ ] Once data available: create **ROAS by Attribution Window** chart (compare 1d, 7d, 28d click windows)
- [ ] Create **Purchase Value by Attribution Window** chart
- [ ] Add to Google Ads section or Advanced Analytics

---

## 3. TikTok Data Cleanup
**Status:** PARTIALLY DONE — 2025 data preserved, 2026 excluded

### Completed:
- [x] Excluded 2026 TikTok data via `WHERE stat_time_day < '2026-01-01'` in `stg_tiktok_spend.sql`
- [x] 2025 TikTok data (365 rows, $36,910) retained in `fact_spend_daily`
- [x] Removed TikTok dashboard section (was 12 dashcards)

### Future:
- [ ] Fix the TikTok Airbyte connector to sync the correct advertiser for 2026
- [ ] Once fixed: remove the date filter from `stg_tiktok_spend.sql`
- [ ] Re-add TikTok section to dashboard (restore from prior config or rebuild)
- [ ] Verify blended metrics (MER, Total Spend) include TikTok correctly

---

## 4. Meta Funnel Visualization Improvements
**Status:** PARTIALLY DONE

### Completed:
- [x] Switched all Meta metrics to use `inline_link_clicks` (link clicks, not all clicks)
- [x] Updated `stg_meta_spend.sql`, `fact_spend_daily` table, and Meta Funnel card
- [x] Added Meta Funnel Conversion Rates table with benchmarks
- [x] Added Unique Link Clicks, Unique CPC, Unique CTR cards
- [x] Renamed cards to clarify: Meta Link Clicks, Meta Link CTR, Meta Link CPC
- [x] Updated glossary with link click / unique definitions

### Future:
- [ ] Consider removing or redesigning the Meta Funnel bar chart — Link Clicks bar dominates
  so visually the ATC/Checkout/Purchase stages are tiny. Options:
  - Remove clicks from the bar chart and start the funnel at ATC
  - Switch to a funnel visualization (if Metabase supports it)
  - Use a waterfall/flow chart instead
  - Keep as-is since the Conversion Rates table provides the detailed view
- [ ] Add Meta outbound clicks as a separate metric if needed (clicks that leave Facebook)

---

## 5. Email / Klaviyo Integration
**Status:** NOT STARTED — Airbyte stream exists (`raw.klaviyo_campaigns`) but no dashboard cards

### Future:
- [ ] Explore `raw.klaviyo_campaigns` table structure and available columns
- [ ] Create staging model `stg_klaviyo.sql`
- [ ] Add Email section to dashboard:
  - Email Revenue
  - Email Revenue % of Total Revenue
  - Open Rate
  - Click Rate
  - Unsubscribe Rate
  - Revenue Per Email Sent
  - Campaign Performance table (top campaigns by revenue)
- [ ] Add email as a channel in Channel Overview / Efficiency Comparison

---

## 6. Dashboard Performance & UX
**Status:** ONGOING

### Future:
- [ ] Dashboard has 95 cards — loads slowly ("You can make this dashboard snappier" warning)
  - Consider splitting into multiple dashboards or using tabs
  - Move Advanced Analytics, Experiments, Data Health to a separate "Deep Dive" dashboard
  - Or use Metabase dashboard tabs feature
- [ ] Some cards don't respect dashboard date filters (Spend Allocation Over Time shows full history)
  - Audit every card's parameter mappings to ensure date filter applies
- [ ] Review compare_mode functionality — some cards compare vs "December 31, 2025" instead of
  the actual previous period. Verify compare_mode template tag is mapped and working correctly.
- [ ] Consider adding a "Data as of" timestamp to the top of the dashboard

---

## 7. dbt Model Maintenance
**Status:** ONGOING — dbt can't currently be run (no profiles.yml configured)

### Future:
- [ ] Set up `profiles.yml` so dbt can be run to rebuild all models
- [ ] Run `dbt run` to ensure all staging views and mart tables match current SQL
- [ ] Current workarounds (direct DB edits via Metabase API) should be validated by a full dbt run
- [ ] The `fact_spend_daily_fx` VIEW definition is in the DB but not tracked as a dbt model —
  consider creating `fact_spend_daily_fx.sql` as a proper dbt model
- [ ] Add dbt tests for data quality (not_null, unique, accepted_values for channel)
- [ ] `stg_meta_spend.sql` references source `ads_insights` but actual table is `meta_ads_insights`
  — verify the dbt source mapping works correctly

---

## 8. Google Ads Section Enhancements
**Status:** NOT STARTED

### Future:
- [ ] Add Google Cost Per ATC, Cost Per Checkout equivalent cards (if Google conversion actions data is available)
- [ ] Add Google unique click metrics if available in raw data
- [ ] Add Search Terms / Keyword performance table (if search terms report is synced)
- [ ] Add Google Ads campaign-level breakdown (top campaigns by spend/ROAS)

---

## 9. Multi-Client Support
**Status:** PARTIALLY DONE — `client_slug` filter exists but only "expand" is active

### Future:
- [ ] When onboarding new clients: ensure all cards use `client_slug` parameter consistently
- [ ] Some cards query `raw.*` tables directly without a client filter — these will break with multiple clients
  - Meta Funnel (card 412): queries raw.meta_ads_insights with no client_slug filter
  - Meta Funnel Conversion Rates (card 424): same issue
  - Unique Link Clicks/CPC/CTR (cards 421-423): same issue
- [ ] Add `client_slug` to raw data queries or create client-aware staging models
- [ ] Currency conversion via `fact_spend_daily_fx` already supports per-client FX rates

---

## 10. Advanced Analytics Expansion
**Status:** NOT STARTED

### Future ideas:
- [ ] **Cohort analysis** — Revenue by acquisition month/week, retention curves
- [ ] **Incrementality testing** framework beyond GeoLift
- [ ] **Forecasting** — Projected revenue/spend based on historical trends
- [ ] **Budget pacing** — Are we on track to hit monthly spend/revenue targets?
- [ ] **Diminishing returns curve** — Spend vs Revenue efficiency at different spend levels
- [ ] **Creative fatigue detection** — CTR/CVR decline over time for campaigns

---

## Quick Reference: Current Dashboard State

### Sections (95 dashcards total):
| Section | Cards | Notes |
|---------|-------|-------|
| Executive KPIs | 19 | Revenue, Spend, MER, ROAS, CPA, LTV:CAC, etc. |
| Customer Metrics | 8 | New/Returning, LTV, AOV, Rev Per Customer |
| Geographic Performance | 3 | Top states, revenue by state |
| Period Comparison | 1 | Current vs prior period table |
| Correlation Analysis | 4 | Frequency vs ROAS, Clicks vs Spend, Auction Efficiency |
| Conversion Funnel | 5 | Total Funnel, Meta Funnel, Platform Breakdown, Stage Rates, Funnel CVR Rates |
| Channel Overview | 2 | Efficiency table, Spend Allocation chart |
| Meta Ads | 17 | Full metrics including unique clicks/CPC/CTR |
| Google Ads | 12 | Core metrics |
| Advanced Analytics | 4 | Day-of-Week, Cumulative, Moving Avg ROAS, ROAS by Platform |
| Experiments | 3 | GeoLift |
| Data Health | 2 | Pipeline status, Data quality |

### Key Technical Details:
- **Metabase API key:** stored in `.env`
- **Database:** Supabase Postgres (Metabase DB ID: 2)
- **dbt:** models in `measurement-platform/dbt/` — can't currently run (no profiles.yml)
- **Meta clicks:** All metrics use `inline_link_clicks` (link clicks), NOT `clicks` (all clicks)
- **TikTok:** 2025 data included, 2026 excluded via date filter in `stg_tiktok_spend.sql`
- **Currency:** `fact_spend_daily_fx` VIEW handles FX conversion via `currency_config` table
