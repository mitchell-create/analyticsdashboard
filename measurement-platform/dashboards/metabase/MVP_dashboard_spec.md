# Metabase MVP dashboard spec

Connect Metabase **only** to the dbt marts schema (or public marts tables). Do not expose raw Airbyte tables for reporting.

---

## Data source

- **Database:** Client Supabase project.
- **Schema / tables:** Use **marts** schema (or equivalent) with:
  - `fact_spend_daily`
  - `fact_kpi_daily`
  - `fact_kpi_geo_daily`
  - `fact_klaviyo_daily`
  - `fact_tiktok_organic_daily`
  - `dim_campaign`
  - `dim_geo`
  - `marketing_events` (public)
  - `experiments`, `experiment_results` (public)

---

## Dashboard 1: Executive Overview

**Purpose:** High-level spend vs revenue and key KPIs.

| Chart | Type | Data | Filters |
|-------|------|------|--------|
| Spend vs revenue over time | Line or area | `fact_spend_daily` (sum spend by date) + `fact_kpi_daily` (revenue by date) | Date range |
| Daily revenue | Line | `fact_kpi_daily.revenue` | Date range |
| Daily orders | Line | `fact_kpi_daily.orders` | Date range |
| Total spend by channel (period) | Bar | `fact_spend_daily` (sum spend by channel) | Date range |
| ROAS (revenue / spend) | Number or trend | `fact_kpi_daily.revenue` / `fact_spend_daily.spend` | Date range |

---

## Dashboard 2: Channel Performance

**Purpose:** ROAS and performance by paid channel.

| Chart | Type | Data | Filters |
|-------|------|------|--------|
| Spend by channel over time | Line | `fact_spend_daily` (spend by date, channel) | Date range, channel |
| ROAS by channel | Bar or table | Join `fact_spend_daily` (sum spend by channel) to `fact_kpi_daily` (revenue); compute ROAS | Date range |
| Impressions / clicks by channel | Line or table | `fact_spend_daily` (impressions, clicks by date, channel) | Date range, channel |
| Spend share by channel (pie) | Pie | `fact_spend_daily` (sum spend by channel) | Date range |

---

## Dashboard 3: Organic TikTok + Email Context

**Purpose:** Organic TikTok activity and email campaign context.

| Chart | Type | Data | Filters |
|-------|------|------|--------|
| TikTok organic views over time | Line | `fact_tiktok_organic_daily.views` | Date range |
| TikTok organic engagement (likes, comments, shares) | Line | `fact_tiktok_organic_daily` (likes, comments, shares) | Date range |
| TikTok followers over time | Line | `fact_tiktok_organic_daily.followers` | Date range |
| Email sends / opens / clicks by day | Line or table | `fact_klaviyo_daily` (sent, opens, clicks by report_date) | Date range |
| Marketing events timeline | Timeline or list | `marketing_events` (event_date, event_type, event_name) | Date range |

Use `marketing_events` to annotate or filter when interpreting TikTok and email trends (e.g. email blasts, promos).

---

## Dashboard 4: Experiment Results

**Purpose:** Incrementality and lift test results (GeoLift, CausalImpact).

| Chart | Type | Data | Filters |
|-------|------|------|--------|
| Experiments list | Table | `experiments` (experiment_slug, experiment_type, start_date, end_date, status) | Status, type |
| Lift over time (per experiment) | Line | `experiment_results` (result_date, value, interval_lower, interval_upper by experiment_id, metric) | Experiment, metric |
| Latest lift summary | Table or cards | `experiment_results` joined to `experiments` (latest result_date per experiment) | Experiment type |

Connect only to `experiments` and `experiment_results`; model runner writes results there.

---

## Filters (global where possible)

- **Date range:** Apply to all dashboards (report_date, event_date, result_date as appropriate).
- **Channel:** On Channel Performance (meta, google, tiktok).
- **Experiment:** On Experiment Results.

---

## Implementation notes

1. Create one Metabase database connection per client (Supabase project).
2. Sync only marts + `marketing_events`, `experiments`, `experiment_results`; do not sync raw Airbyte schema.
3. Clone or duplicate these dashboards per client and point to that client’s DB.
4. Use Metabase questions (saved SQL or GUI) for ROAS and custom metrics; reuse across dashboards where possible.
