# Add Meta (Facebook/Instagram) Ads data

What needs to be added so Meta spend shows in your Executive Overview and Channel Performance dashboards.

---

## 1. Airbyte — add Meta Ads source (required)

This is the **only new piece** you add from scratch.

1. **In Airbyte:** Create a new **Source**.
2. **Connector:** Choose **Facebook Marketing** (Meta Ads).
3. **Credentials:** You need:
   - **Ad Account ID** — from Meta Business Suite / Ads Manager (e.g. `act_123456789`).
   - **Access token** — from [Meta for Developers](https://developers.facebook.com/) → your app → Tools → Graph API Explorer (or System User token for long‑lived).
4. **Streams to sync:** Enable at least:
   - **Ads Insights** (or **Insights** / daily breakdown) — this is what dbt expects for daily spend, impressions, clicks.
5. **Destination:** Your existing Supabase connection (Session pooler, port 5432).
6. **Schema/namespace:** Use `public` or a dedicated schema (e.g. `raw`). If you use `raw`, create the schema in Supabase first (e.g. `CREATE SCHEMA IF NOT EXISTS raw;`).
7. **Run sync:** Do a full sync first; backfill last 90 days if the connector supports it.

After the first sync, note the **exact table name** Airbyte created (e.g. `ads_insights`, `AdsInsights`, or `_airbyte_raw_ads_insights`). You’ll need it for step 2.

---

## 2. dbt — point to the real Meta table (only if needed)

The repo already has:

- **Staging:** `dbt/models/staging/stg_meta_spend.sql` — reads from `raw_airbyte.meta_ads_insights_daily`.
- **Marts:** `fact_spend_daily` unions Meta + Google + TikTok; it already includes `stg_meta_spend`.

**If** Airbyte created a table with a **different name** (e.g. `ads_insights` in `public`):

1. **Option A — same schema/table name:**  
   In Airbyte destination config, set the stream’s table name to `meta_ads_insights_daily` and schema to `raw` (if you use `raw`). Then ensure the `raw` schema exists in Supabase. No dbt change.

2. **Option B — update dbt to match Airbyte:**  
   Edit `dbt/models/sources.yml`: under `raw_airbyte.tables`, set the Meta table’s `name` to the actual Airbyte table (e.g. `ads_insights`). If the table is in `public`, add a source that uses `schema: public` for that table, or set `raw_schema` to `public` for this project.  
   Then edit `dbt/models/staging/stg_meta_spend.sql`: use the column names Airbyte actually writes. Often Airbyte writes a JSONB column like `_airbyte_data`; then you’d use the “uncomment” block in that file and map `date_start`, `spend`, `impressions`, `clicks` from `_airbyte_data`.

---

## 3. Run dbt (after raw Meta data exists)

From the dbt project folder:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dbt"
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"
dbt run --select stg_meta_spend fact_spend_daily
```

Then in Metabase, refresh the Executive Overview (and Channel Performance if you built it); “Spend by date” and “Total spend by channel” should show Meta.

---

## Summary: what to add

| What | Action |
|------|--------|
| **Airbyte** | Add **Meta Ads (Facebook Marketing)** source; configure Ad Account ID + access token; sync **Ads Insights** (daily); destination = Supabase. |
| **Supabase** | No new schema required unless you choose a `raw` schema — then `CREATE SCHEMA IF NOT EXISTS raw;` once. |
| **dbt** | No code change if Airbyte table is `raw.meta_ads_insights_daily` with columns like `insight_date`, `spend`, `impressions`, `clicks`. Otherwise update `sources.yml` and `stg_meta_spend.sql` to match the real table/columns. |
| **Metabase** | Nothing to add; existing Executive Overview and Channel Performance use `fact_spend_daily`. |

So the **only thing you must add** is the **Meta Ads source in Airbyte**. The rest is aligning table/column names and running dbt once the raw data is there.
