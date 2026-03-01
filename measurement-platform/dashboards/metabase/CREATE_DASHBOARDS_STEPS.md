# Exact steps: Create MVP dashboards via Metabase API

Do this **after** Metabase is running and connected to your Supabase database (see [METABASE_SETUP.md](METABASE_SETUP.md)).

---

## Prerequisites

- Metabase running at **http://localhost:3000**
- You have already added the Supabase database in Metabase and synced schemas
- You know your Metabase **admin email** and **password** (the account you created in the setup wizard)

---

## Step 1: Open PowerShell

Open a new PowerShell window (or use the terminal in Cursor).

---

## Step 2: Install the `requests` library (one-time)

Run:

```powershell
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m pip install requests
```

You should see something like `Successfully installed requests-...`. If you already have it, that’s fine.

---

## Step 3: Go to the metabase folder

Run (use the path in quotes because of the space):

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
```

---

## Step 4: Set your Metabase login (this session only)

Replace with the **email** you use to log in to Metabase and your **Metabase password**. Run both lines:

```powershell
$env:METABASE_EMAIL="mitchell@nexocore.ca"
$env:METABASE_PASSWORD="YourPassword"
```

*(Optional)* If Metabase is not on port 3000:

```powershell
$env:METABASE_URL="http://localhost:3000"
```

---

## Step 5: Run the script

Run:

```powershell
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe create_mvp_dashboards.py
```

---

## Step 6: Check the output

You should see something like:

```
Using database id: 2
Created dashboard: Executive Overview (id=1)
  Added card: Daily revenue (id=1)
  Added card: Daily orders (id=2)
  ...

Done. Open http://localhost:3000/dashboard/1
```

- If you see **"Login failed"**: double-check `METABASE_EMAIL` and `METABASE_PASSWORD` (Step 4) and try again.
- If you see **"No database found"**: add and save your Supabase database in Metabase first (Settings → Databases → Add database), then run the script again.
- If some cards show **"Skipped"** or errors: those use tables (e.g. `fact_spend_daily`) that may not exist yet; run the right dbt models, then re-run the script or add those questions manually later.

---

## Step 7: Open the dashboard

In your browser, go to the URL printed at the end, e.g.:

**http://localhost:3000/dashboard/1**

(Use the dashboard ID from the script output if it’s different.)

You should see the **Executive Overview** dashboard with the cards that were created successfully.

---

## Alternative: Use an API key instead of password

If you prefer not to use your password in the terminal:

1. In Metabase, go to **Settings** (gear) → **Admin settings** → **Authentication** → **API Keys** (or **Account settings** → **API Keys** depending on your version).
2. Click **Create API key**, give it a name (e.g. "Dashboard script"), copy the key.
3. In PowerShell, set it (and run the script in the same session):

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
$env:METABASE_API_KEY="your-copied-api-key-here"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe create_mvp_dashboards.py
```

You do **not** need `METABASE_EMAIL` or `METABASE_PASSWORD` when `METABASE_API_KEY` is set.

---

## Quick copy-paste summary (email + password)

Replace the password, then run in order:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
$env:METABASE_EMAIL="mitchell@nexocore.ca"
$env:METABASE_PASSWORD="YourPassword"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe create_mvp_dashboards.py
```

Then open in the browser the URL shown at the end (e.g. `http://localhost:3000/dashboard/1`).

---

## Manual option: Copy SQL from files

If the API script fails or you prefer to build dashboards manually, use the SQL files in `sql/`:

- `sql/01_executive_overview/` — 5 charts
- `sql/02_channel_performance/` — 4 charts
- `sql/03_email_klaviyo/` — 3 charts
- `sql/04_experiment_results/` — 3 charts

See `sql/README.md` for chart types and setup steps.
