# Metabase self-hosted setup (analytics-dashboard)

Use this after you have **metabase.jar** and want to connect to your Supabase warehouse.

**For a full step-by-step guide including dashboard creation, see [METABASE_DASHBOARD_SETUP.md](METABASE_DASHBOARD_SETUP.md).**

---

## 1. Run Metabase

**Prerequisite:** Java 21 or higher (Metabase requirement). Check with `java -version`. Use OpenJDK or Oracle JDK (e.g. [Adoptium Temurin 21 LTS](https://adoptium.net)).

**Where:** Open a terminal. Go to the folder where **metabase.jar** is (or use the full path to the JAR).

**Run:**

```
java -jar metabase.jar
```

**You should see:** Logs like "Metabase Initialization complete" and "Starting Jetty". Metabase will create a `metabase.db` file in that folder (SQLite) for its own data.

**URL:** Open a browser and go to **http://localhost:3000** (default port).

---

## 2. First-time setup (admin account)

1. At **http://localhost:3000** you’ll see "Welcome to Metabase".
2. Click **Let's get started**.
3. Enter your **admin** details (name, email, password) and click **Next**.
4. **Add your organization's data** — click **I'll add my data later** (or **Next**) so you can add the database in the next step.
5. Finish the wizard (you can skip "Usage data" if you want).

---

## 3. Add Supabase (analytics-dashboard) as a database

1. In Metabase, go to **Settings** (gear icon) → **Admin settings** → **Databases** (or **Databases** in the left sidebar under Admin).
2. Click **Add database**.
3. Fill in:

   | Field | Value |
   |-------|--------|
   | **Database type** | PostgreSQL |
   | **Display name** | Analytics Dashboard (or any name) |
   | **Host** | `aws-1-us-east-2.pooler.supabase.com` |
   | **Port** | `5432` |
   | **Database name** | `postgres` |
   | **Username** | `postgres.xopsomagbnsnadxxhzhx` |
   | **Password** | Your Supabase database password (same as in dbt profiles.yml) |
   | **Use a secure connection (SSL)** | On (or **Yes**) |

4. Click **Save** (or **Test connection** first, then **Save**).
5. If Metabase asks which schemas to sync: include **public** and **public_marts** (or **marts** if you see it). Sync so Metabase can see your tables.

---

## 4. Sync and use the right tables

- After saving, Metabase will sync. You should see **public_marts** (or **marts**) with tables like **fact_kpi_daily**, **dim_geo**, **fact_spend_daily**, etc., and **public** with **marketing_events**, **experiments**, **experiment_results**.
- For dashboards, use **only** the marts (and public tables like **marketing_events**, **experiments**, **experiment_results**). Do **not** build reports from raw Airbyte tables (e.g. raw.orders).

---

## 5. Build dashboards (choose one)

### Option A: API script (recommended — no manual clicking)

A script creates the **Executive Overview** dashboard and its questions via the Metabase API.

1. Install: `pip install requests`
2. Set env (or use `.env`):  
   `METABASE_URL=http://localhost:3000` (default)  
   `METABASE_EMAIL=` your Metabase admin email  
   `METABASE_PASSWORD=` your Metabase admin password  
   Or use an [API key](https://www.metabase.com/docs/latest/people-and-groups/api-keys): `METABASE_API_KEY=...`
3. From the repo root or `dashboards/metabase/` run:
   ```powershell
   cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
   $env:METABASE_EMAIL="mitchell@nexocore.ca"; $env:METABASE_PASSWORD="your-password"
   python create_mvp_dashboards.py
   ```
4. Open the URL printed at the end (e.g. `http://localhost:3000/dashboard/1`).

Cards that reference tables you don’t have yet (e.g. `fact_spend_daily`) will be skipped or may show errors until you run the corresponding dbt models.

### Option B: Manual (or Cursor browser)

1. Go to **Browse data** (or **New** → **Dashboard**).
2. Create a **new dashboard** (e.g. "Executive Overview").
3. Add a **question** (chart):
   - **Data** → **Simple question** (or **Native query**).
   - Pick **public_marts** (or **marts**) → **fact_kpi_daily**.
   - Choose **Summarize** → **Sum of revenue** (or **Sum of orders**), group by **report_date**.
   - Visualize as **Line** or **Bar** and **Add to dashboard**.
4. Repeat for other charts. Full list: **[MVP_dashboard_spec.md](MVP_dashboard_spec.md)**.

You can also ask the AI to use **Cursor’s browser** to open Metabase and build the dashboards by clicking (have Metabase running and log in first).

---

## 6. Optional: run Metabase in the background

To keep Metabase running after you close the terminal (Windows):

- Run it in the background, or
- Use **nohup** / **Start-Process** (PowerShell), or
- Install and run as a Windows service (e.g. with a wrapper or NSSM).

Example (PowerShell, new window):

```powershell
Start-Process java -ArgumentList "-jar", "C:\path\to\metabase.jar" -WindowStyle Hidden
```

(Replace `C:\path\to\metabase.jar` with the real path.)

---

## Checklist

- [ ] Java 11+ installed; `java -jar metabase.jar` runs; http://localhost:3000 loads.
- [ ] Admin account created.
- [ ] PostgreSQL database added (Supabase host, port 5432, user, password, SSL on).
- [ ] Schemas **public** and **public_marts** (or **marts**) synced and visible.
- [ ] First dashboard created using **fact_kpi_daily** (and **MVP_dashboard_spec.md** for more charts).
