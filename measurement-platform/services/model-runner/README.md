# Model Runner — GeoLift & CausalImpact

Runs lift experiments (GeoLift for geo holdouts, CausalImpact for time-series) and writes results to Supabase.

---

## Prerequisites

1. **Python 3.10+** with `pip install -r requirements.txt`
2. **R** (https://cran.r-project.org/) with:
   - `CausalImpact`: `install.packages("CausalImpact")`
   - `zoo`: `install.packages("zoo")`
   - For GeoLift: `remotes::install_github("facebookincubator/GeoLift")`
3. **Rscript** on PATH (comes with R)

---

## Step 1: Create experiments tables in Supabase

Run the SQL from `warehouse/schema/040_experiments.sql` in Supabase SQL Editor:

```sql
CREATE TABLE IF NOT EXISTS public.experiments (
  id            BIGSERIAL PRIMARY KEY,
  experiment_slug TEXT NOT NULL UNIQUE,
  experiment_type TEXT NOT NULL,
  start_date   DATE NOT NULL,
  end_date     DATE NOT NULL,
  config       JSONB,
  status       TEXT NOT NULL DEFAULT 'draft',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.experiment_results (
  id            BIGSERIAL PRIMARY KEY,
  experiment_id BIGINT NOT NULL REFERENCES public.experiments (id),
  result_date   DATE NOT NULL,
  metric        TEXT NOT NULL,
  value         NUMERIC(18, 4),
  interval_lower NUMERIC(18, 4),
  interval_upper NUMERIC(18, 4),
  metadata      JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (experiment_id, result_date, metric)
);
```

---

## Step 2: Set environment variables

```powershell
$env:SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
$env:SUPABASE_SERVICE_KEY = "your-service-role-key"

# Required for reading from public_marts (dbt tables)
$env:SUPABASE_DB_URL = "postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
```

**Get SUPABASE_DB_URL:** Supabase Dashboard → **Settings** → **Database** → **Connection string** (URI). Use the "Transaction" pooler URL and replace `[YOUR-PASSWORD]` with your database password.

---

## Step 3: Install Python dependencies

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\services\model-runner"
pip install -r requirements.txt
```

---

## Step 4: Install R packages

Open **R** or **RStudio** and run:

```r
install.packages("CausalImpact")
install.packages("zoo")
# Optional for GeoLift:
# remotes::install_github("facebookincubator/GeoLift")
```

---

## Usage

### CausalImpact (time-series lift)

Measures the impact of an intervention (e.g. campaign launch) on revenue or orders.

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\services\model-runner\src"
python runner.py causalimpact my-campaign-2024 2024-01-01 2024-02-28 2024-01-15 revenue
```

- `my-campaign-2024` — experiment slug
- `2024-01-01` — start date
- `2024-02-28` — end date
- `2024-01-15` — intervention date (campaign start)
- `revenue` — metric (revenue | orders)

### GeoLift (geo holdouts)

Requires `fact_kpi_geo_daily` with real geo-level revenue. Currently that table is a placeholder (zeros). When you have geo data:

```powershell
python runner.py geolift my-geo-test 2024-01-01 2024-02-28 "TX,CA" "NY,FL"
```

---

## Step 5: Metabase Experiment Results dashboard

1. In Metabase, create a new dashboard **Experiment Results**.
2. Add a **Table** question: `SELECT * FROM experiments ORDER BY created_at DESC`
3. Add a **Line chart**: `SELECT result_date, value, interval_lower, interval_upper FROM experiment_results WHERE experiment_id = {{experiment_id}} AND metric = 'revenue'`
4. Add a filter for **Experiment** (experiment_slug or experiment_id).

See `dashboards/metabase/MVP_dashboard_spec.md` for full spec.

---

## Troubleshooting

**"relation public_marts.fact_kpi_daily does not exist"**  
- Ensure dbt has been run (`dbt run`) so marts tables exist.
- Set `SUPABASE_DB_URL` for direct database access.

**"CausalImpact not installed"**  
- Run `install.packages("CausalImpact")` in R.

**"Rscript not found"**  
- Add R's `bin` folder to PATH (e.g. `C:\Program Files\R\R-4.4.0\bin`).
