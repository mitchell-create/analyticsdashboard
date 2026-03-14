# Google Analytics Integration — Task Tracker
# Status: PENDING (waiting for GA to be connected via Airbyte)

## Priority 1 — Core Metrics (add to dashboard immediately when GA is live)

### Website Sessions
- Add `sessions` to `fact_kpi_daily` (or new `fact_ga_daily` model)
- Create **Website CVR** executive KPI card: Orders / Sessions x 100
- Display alongside existing **Paid CVR** (Orders / Ad Clicks) for comparison
- Add **Cost Per Session** card: Total Ad Spend / Sessions

### Full Website Funnel (replace current 2-stage Total Funnel)
- Sessions -> Product Page Views -> Add to Cart -> Checkout -> Purchase
- Stage conversion rates between each step
- Cart Abandonment Rate: 1 - (Checkouts / ATCs)
- Checkout Abandonment Rate: 1 - (Purchases / Checkouts)

### Website CVR vs Paid CVR Comparison Chart
- Daily line chart: Website CVR (sessions-based) vs Paid CVR (clicks-based)
- 7-day rolling average to smooth daily noise (same pattern as existing Paid CVR vs ROAS chart)

## Priority 2 — Traffic Quality & Channel Breakdown

### Sessions by Source/Medium
- Organic vs Paid vs Direct vs Referral vs Email breakdown
- Stacked area chart over time
- Useful for understanding non-paid traffic contribution

### Bounce Rate by Channel
- Table or bar chart: bounce rate per traffic source
- Helps assess ad landing page quality

### New vs Returning Visitors
- Pairs with existing New Customers / Returning Customers Shopify metrics
- Session-level new vs returning breakdown

## Priority 3 — Efficiency & Engagement

### Revenue Per Session
- Revenue / Sessions — site-wide monetization metric
- Trend over time as line chart

### Average Pages per Session
- Engagement depth indicator
- Can correlate with conversion rate

### Landing Page Performance
- Top landing pages by conversion rate
- Landing page bounce rate — are ads sending traffic to the right pages

## Implementation Notes

### Data Pipeline
- Source: Google Analytics 4 (GA4) via Airbyte
- Key GA4 tables to sync: `analytics_XXX.events_*` or pre-aggregated reports
- Staging model: `stg_ga_sessions.sql` (daily sessions, source/medium, new vs returning)
- Mart model: `fact_ga_daily.sql` (aggregated daily metrics)
- Update `fact_kpi_daily` to include sessions column, or join GA data at the card level

### Dashboard Cards to Create
- Website CVR (smartscalar, Executive KPIs row)
- Cost Per Session (smartscalar, Executive KPIs row or Channel Overview)
- Full Funnel chart (bar chart, replace current Total Funnel)
- Website CVR vs Paid CVR (line chart, Correlation Analysis)
- Sessions by Source (stacked area, new Channel Overview section)
- Cart/Checkout Abandonment Rates (smartscalar or table)

### Dashboard Cards to Update
- Total Funnel: expand from Clicks -> Orders to full Sessions -> ATC -> Checkout -> Purchase
- Stage Conversion Rates table: add session-based rates
- Glossary text card: add Website CVR definition
