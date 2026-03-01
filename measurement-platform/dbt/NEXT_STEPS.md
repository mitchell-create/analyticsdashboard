# dbt setup — simple step-by-step (analytics-dashboard)

Follow these steps in order. Do one step, then the next.

---

## Step 1: Install dbt

**What you’re doing:** Installing the dbt tool and its Postgres connector.

**Where:** Open a terminal (PowerShell or Command Prompt) in this project.

**Type this and press Enter** (use the full path so the terminal finds Python):

```
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe -m pip install dbt-postgres
```

**You should see:** Something like “Successfully installed dbt-postgres…” at the end.

**If you get “Python was not found”** when you type `python` by itself, that’s normal — your terminal doesn’t have Python on its PATH. Always use the full path above for `python` and `pip`, or see “Optional: make `python` work in terminal” at the end of this doc.

---

## Step 2: Go to the dbt folder and make `dbt` available

**What you’re doing:** Moving into the dbt project folder and making the `dbt` command work in this terminal.

**Type these two lines, one at a time** (the second adds Python’s Scripts folder to this terminal so `dbt` is found). **Use quotes around the path because it has a space:**

```
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dbt"
$env:Path += ";C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\Scripts"
```

**You should see:** Your prompt shows the dbt folder path. After the second line, typing `dbt --version` should work.

---

## Step 3: Copy the profile template

**What you’re doing:** Creating your own `profiles.yml` from the template (so you can put your password in it without changing the template).

**Type this and press Enter:**

```
copy profiles.yml.template profiles.yml
```

**You should see:** “1 file(s) copied.”

---

## Step 4: Get your Supabase database password

**What you’re doing:** Finding the password dbt will use to connect to Supabase.

1. Open your browser and go to [supabase.com/dashboard](https://supabase.com/dashboard).
2. Open your **analytics-dashboard** project.
3. Click **Settings** (gear icon) in the left sidebar.
4. Click **Database**.
5. Under “Database password,” either use the one you set when you created the project, or click **Reset database password**, set a new one, and copy it somewhere safe (you’ll paste it in the next step).

---

## Step 5: Put your password into profiles.yml

**What you’re doing:** Telling dbt how to connect to your Supabase database.

1. In your project, open the file: **measurement-platform/dbt/profiles.yml** (in Cursor/VS Code or Notepad).
2. Find the line that says `password: "{{ env_var('SUPABASE_DB_PASSWORD', '') }}"` under the `dev:` section.
3. Replace that whole line with your actual password in quotes, for example:
   - `password: "mySecretPassword123"`
   - Use the password from Step 4. Keep the quotes.
4. Check that these lines under `dev:` look exactly like this (no typos):
   - `host: "aws-1-us-east-2.pooler.supabase.com"`
   - `port: 5432`
   - `user: "postgres.xopsomagbnsnadxxhzhx"`
   - `dbname: postgres`
   - `schema: public`
5. Save the file.

---

## Step 6: Install dbt dependencies

**What you’re doing:** Letting dbt download any extra packages it needs.

**Where:** Same terminal, still in the dbt folder (from Step 2). If you closed it, run the `cd` command from Step 2 again.

**Type this and press Enter:**

```
dbt deps
```

**You should see:** “Installing …” and then “Finished …” with no red errors. It’s okay if it says “no dependencies” or similar.

---

## Step 7: Load the geography seed data

**What you’re doing:** Loading the list of US states into your database (for geo reports later).

**Type this and press Enter:**

```
dbt seed
```

**You should see:** “Completed successfully” or “1 of 1 … OK”. No red errors.

---

## Step 8: Build the Shopify → daily KPI models

**What you’re doing:** Reading your Shopify orders from Supabase and building the daily revenue/orders table.

**Type this and press Enter:**

```
dbt run --select stg_shopify_orders fact_kpi_daily
```

**You should see:**  
- “Running with dbt…”  
- “Completed successfully” and “Done.”  
- It may say “1 of 2 … OK” and “2 of 2 … OK”.

**If you see an error** about a column (e.g. `created_at` or `total_price` not found):  
- In Supabase, go to Table Editor → schema **raw** → table **orders**.  
- Note the exact column names you see.  
- Send me that list and I’ll fix the model.

---

## Step 9: Run the tests

**What you’re doing:** Checking that the data and models look correct.

**Type this and press Enter:**

```
dbt test
```

**You should see:** “Completed successfully” and “Done.” Some tests might be skipped (that’s okay). If any test **fails**, you can send me the error message and I’ll help fix it.

---

## Step 10: Check the result in Supabase

**What you’re doing:** Confirming the new tables exist and have data.

1. In Supabase, open **Table Editor**.
2. At the top, use the schema dropdown and select **marts** (if you see it).
3. Open the table **fact_kpi_daily**.
4. You should see rows with **report_date**, **revenue**, and **orders** — one row per day from your Shopify orders.

---

## Done

You’ve connected dbt to analytics-dashboard, loaded seed data, built the Shopify → daily KPI pipeline, and run tests. If anything in a step didn’t match “You should see,” copy the error or message and send it to me and we’ll fix it.
