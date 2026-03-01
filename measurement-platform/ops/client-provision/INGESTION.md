# Data ingestion — Airbyte + Metricool

This doc describes how to connect Airbyte and Metricool to the client Supabase warehouse. Use it when provisioning a new client (Phase 2).

---

## Airbyte

### Destination

- **Type:** Supabase (PostgreSQL).
- **Connection:** Use the client’s Supabase project connection string (Settings → Database → Connection string).
- **Use Session pooler or Direct connection, not Transaction pooler:** Airbyte’s Postgres connector uses JDBC and often relies on PREPARE statements. Supabase’s **Transaction pooler** (port 6543) does not support PREPARE and can cause “Connection timed out after 30000ms” or HikariPool errors. In Supabase, switch the connection string dropdown to **Session pooler** (port 5432) or **Direct connection** and use that host/port in Airbyte.
- **Username:** Must match exactly (e.g. `postgres.<project_ref>` for pooler). A typo (e.g. `postgres.xopsomagbsnnadxxhzhx` vs `postgres.xopsomagbnsnadxxhzhx`) will prevent connection.
- **Schema/namespace:** Use a dedicated schema for raw data (e.g. `raw` or `airbyte`) so dbt staging reads from it. Default schema is fine if you prefix raw tables (e.g. `_airbyte_meta_ads_*`).

#### Airbyte → Supabase troubleshooting

| Symptom | Fix |
|--------|-----|
| “Connection timed out after 30000ms” / HikariPool timeout | Use **Session pooler** (port **5432**) or **Direct** DB host (`db.<ref>.supabase.co:5432`), not Transaction pooler (6543). |
| Same timeout | Check **Username** matches Supabase exactly (no extra/missing character in project ref). |
| Auth or connection refused | Ensure **Password** is the real DB password (Settings → Database → Reset password if needed). SSL mode **require** is correct. |

### Sources (create one connection per source)

| Source       | Connector / Notes |
|-------------|--------------------|
| **Meta Ads**   | Facebook Marketing API; need Ad Account ID, access token. Sync: campaigns, ad sets, ads, insights (daily). |
| **Google Ads** | Google Ads API; need Customer ID, OAuth. Sync: campaigns, ad groups, keywords, metrics (daily). |
| **TikTok Ads** | TikTok Marketing API; need Advertiser ID, token. Sync: campaigns, ads, reports (daily). |
| **Shopify**    | Shopify Admin API; need store URL, Admin API token. Sync: orders, customers; normalize to daily revenue/orders for dbt. |
| **Klaviyo**    | Klaviyo API; need API key. Sync: campaigns, metrics (sends, opens, clicks) for daily fact_klaviyo_daily. |

### Sync schedule

- **Initial:** Run full sync for each source.
- **Ongoing:** Daily sync (e.g. 2–4 AM client timezone).
- **Incremental:** Use connector’s recommended incremental column (e.g. `updated_at`, `date`) where supported to avoid full reloads.

### Raw table naming

Airbyte typically creates tables like `_airbyte_raw_<stream_name>`. Document the exact stream → table mapping for this workspace so dbt staging models reference the correct tables.

---

## Metricool

### Purpose

- Ingest **TikTok organic** account-level metrics (views, likes, comments, shares, followers) by day.

### Setup

1. Connect the client’s TikTok account in Metricool.
2. Configure export or API sync into Supabase:
   - **Option A:** Metricool → webhook/API → custom loader that inserts into `fact_tiktok_organic_daily` (or a raw staging table).
   - **Option B:** Metricool export (CSV/API) → scheduled job (e.g. Prefect, cron) that loads into a raw table; dbt model builds `fact_tiktok_organic_daily`.
3. Ensure **report_date** and metric columns align with warehouse schema: `report_date`, `views`, `likes`, `comments`, `shares`, `followers`.

### Sync schedule

- **Daily:** Pull previous day’s metrics (e.g. after midnight).
- **Backfill:** One-time pull for historical range (e.g. 90 days or 12 months) when onboarding.

---

## Backfill strategy

1. **Start:** Backfill last **90 days** for all sources (Airbyte + Metricool) so initial dashboards and experiments have enough history.
2. **Expand:** If needed, extend Airbyte syncs to **12–24 months** for long-run trend and GeoLift/CausalImpact (more pre-period data improves models).
3. **Nightly refresh:** After go-live, only refresh the last **14–30 days** for incremental runs (or use each connector’s incremental settings) to keep runtimes short and avoid re-syncing full history daily.

---

## Checklist (per client)

- [ ] Airbyte workspace created/assigned; destination = this client’s Supabase.
- [ ] All five Airbyte sources connected and mapped to raw tables.
- [ ] Initial full sync run for each source; backfill 90 days (or 12–24 months if required).
- [ ] Daily schedule set (e.g. 2–4 AM).
- [ ] Metricool TikTok account connected; daily sync into Supabase (raw or fact_tiktok_organic_daily).
- [ ] Backfill Metricool 90 days (or 12–24 months).
- [ ] Document raw table names and schema for dbt staging in this repo (e.g. in dbt `sources.yml` or ops doc).
