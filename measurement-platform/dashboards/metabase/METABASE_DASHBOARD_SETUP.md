# Metabase dashboard setup — step-by-step

Follow these steps in order. Do one step, then the next.

---

## Part 1: Prerequisites

### 1.1 Install Java 21+

Metabase requires Java 21 or higher.

1. Open PowerShell and run: `java -version`
2. If you see "version 21" or higher, you're good.
3. If not, download [Adoptium Temurin 21 LTS](https://adoptium.net) and install it.
4. Close and reopen PowerShell, then run `java -version` again.

### 1.2 Download Metabase

1. Go to [metabase.com/start/oss](https://www.metabase.com/start/oss) or [github.com/metabase/metabase/releases](https://github.com/metabase/metabase/releases).
2. Download **metabase.jar** (the standalone JAR, not the Docker image).
3. Save it somewhere easy to find (e.g. `C:\metabase\metabase.jar`).

### 1.3 Get your Supabase database password

1. Go to [supabase.com/dashboard](https://supabase.com/dashboard).
2. Open your **analytics-dashboard** project.
3. Click **Settings** (gear) → **Database**.
4. Under "Database password," use the one you set, or click **Reset database password** and copy the new one.
5. Save it — you'll need it in Part 2.

---

## Part 2: Start Metabase and create admin account

### 2.1 Start Metabase

1. Open **PowerShell**.
2. Go to the folder where metabase.jar is (or use the full path):
   ```powershell
   cd C:\metabase
   ```
   (Replace `C:\metabase` with your actual path.)
3. Run:
   ```powershell
   java -jar metabase.jar
   ```
4. Wait until you see "Metabase Initialization complete" and "Starting Jetty".
5. Leave this window open — Metabase must keep running.

### 2.2 Create admin account (first time only)

1. Open a browser and go to **http://localhost:3000**.
2. You should see "Welcome to Metabase".
3. Click **Let's get started**.
4. Enter:
   - **First name** (e.g. your name)
   - **Email** (e.g. your-email@example.com) — save this; you'll use it for the script
   - **Password** — create a strong password and save it
5. Click **Next**.
6. On "Add your data" — click **I'll add my data later** (or **Next**).
7. Finish the wizard (you can skip "Usage data" if you want).
8. You should land on the Metabase home screen.

---

## Part 3: Add Supabase as a database

### 3.1 Open database settings

1. In Metabase, click the **gear icon** (top right) → **Admin settings**.
2. In the left sidebar, click **Databases** (or **Databases** under "Admin").
3. Click **Add database**.

### 3.2 Fill in connection details

Use **one** of these connection options.

**Option A — Pooler (Session mode):**

| Field | Value |
|-------|-------|
| **Database type** | PostgreSQL |
| **Display name** | Analytics Dashboard |
| **Host** | `aws-1-us-east-2.pooler.supabase.com` |
| **Port** | `5432` |
| **Database name** | `postgres` |
| **Username** | `postgres.xopsomagbnsnadxxhzhx` |
| **Password** | Your Supabase database password from 1.3 |
| **Use a secure connection (SSL)** | On |

**Option B — Direct connection:**

| Field | Value |
|-------|-------|
| **Database type** | PostgreSQL |
| **Display name** | Analytics Dashboard |
| **Host** | `db.xopsomagbnsnadxxhzhx.supabase.co` |
| **Port** | `5432` |
| **Database name** | `postgres` |
| **Username** | `postgres` |
| **Password** | Your Supabase database password from 1.3 |
| **Use a secure connection (SSL)** | On |

### 3.3 Save and sync

1. Click **Save** (or **Test connection** first to verify, then **Save**).
2. Metabase will sync. Wait for it to finish.
3. If Metabase asks which schemas to sync: ensure **public** and **public_marts** are included. Click **Sync database** or **Save**.
4. You should see tables under **public_marts** (fact_kpi_daily, fact_spend_daily, etc.) and **public** (experiments, experiment_results).

---

## Part 4: Create dashboards via script

### 4.1 Install Python dependency

1. Open a **new** PowerShell window (keep Metabase running in the first).
2. Run:
   ```powershell
   C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m pip install requests
   ```

### 4.2 Go to the metabase folder

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
```

### 4.3 Set your Metabase credentials

Replace with the **email** and **password** you used when creating the Metabase admin account (Part 2.2):

```powershell
$env:METABASE_EMAIL = "your-email@example.com"
$env:METABASE_PASSWORD = "YourMetabasePassword"
```

If Metabase is not on port 3000:

```powershell
$env:METABASE_URL = "http://localhost:3000"
```

### 4.4 Run the script

```powershell
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe create_mvp_dashboards.py
```

### 4.5 Check the output

You should see something like:

```
Using database id: 2

Created dashboard: Executive Overview (id=1)
  Added card: Daily revenue (id=1)
  Added card: Daily orders (id=2)
  ...
Created dashboard: Channel Performance (id=2)
  ...
Created dashboard: Email & Klaviyo (id=3)
  ...
Created dashboard: Experiment Results (id=4)
  ...

  -> http://localhost:3000/dashboard/1

Done.
```

### 4.6 Open the dashboards

1. In your browser, go to **http://localhost:3000**.
2. Click **Dashboards** in the left sidebar (or the house icon).
3. You should see: **Executive Overview**, **Channel Performance**, **Email & Klaviyo**, **Experiment Results**.
4. Click any dashboard to view it.

---

## Part 5: Troubleshooting

### "Login failed"

- Double-check `METABASE_EMAIL` and `METABASE_PASSWORD` (Step 4.3).
- Ensure the email and password match the admin account you created in Part 2.2.

### "No database found"

- Add your Supabase database in Metabase first (Part 3).
- After adding, run the script again.

### "relation public_marts.fact_xxx does not exist"

- Your dbt schema might be different. In Supabase SQL Editor, run:
  ```sql
  SELECT schemaname, tablename FROM pg_tables WHERE tablename = 'fact_kpi_daily';
  ```
- If the schema is `marts` (not `public_marts`), the script will fail. You may need to update the SQL in `create_mvp_dashboards.py` to use `marts` instead of `public_marts`.

### Some cards show "Error" or no data

- Run `dbt run` to ensure all marts exist and have data.
- Check that the Prefect pipeline has run successfully.

### Alternative: Use API key instead of password

1. In Metabase, go to **Settings** → **Admin settings** → **Authentication** → **API Keys**.
2. Click **Create API key**, name it (e.g. "Dashboard script"), copy the key.
3. In PowerShell:
   ```powershell
   cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
   $env:METABASE_API_KEY = "your-copied-api-key"
   C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe create_mvp_dashboards.py
   ```
   You do **not** need `METABASE_EMAIL` or `METABASE_PASSWORD` when using the API key.

---

## Part 6: Manual setup (if script fails)

If the script doesn't work, you can create dashboards manually:

1. In Metabase, click **New** → **Dashboard**.
2. Name it (e.g. "Executive Overview") and click **Create**.
3. Click **Add a saved question** or **Add question** → **Native query**.
4. Select your **Analytics Dashboard** database.
5. Copy the SQL from one of the files in `sql/01_executive_overview/` (e.g. `daily_revenue.sql`).
6. Paste into the query editor, click **Run**.
7. Choose the visualization (Line, Bar, Pie, Table).
8. Click **Save** and add to the dashboard.
9. Repeat for each chart. See `sql/README.md` for the full list and chart types.

---

## Quick reference: Full command sequence

```powershell
# Terminal 1: Start Metabase (leave running)
cd C:\metabase
java -jar metabase.jar

# Terminal 2: After Metabase is running and connected to Supabase
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m pip install requests
$env:METABASE_EMAIL = "your-email@example.com"
$env:METABASE_PASSWORD = "YourPassword"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe create_mvp_dashboards.py
```

Then open **http://localhost:3000** and go to **Dashboards**.
