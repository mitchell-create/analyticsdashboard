# Metabase Comparison Dashboard Setup

Period-over-period comparison: "Last N days vs Previous N days" with % change.

---

## Step 1: Run the script

With Metabase running and credentials set:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
$env:METABASE_EMAIL = "your-email"
$env:METABASE_PASSWORD = "your-password"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe create_comparison_dashboard.py
```

This creates the **Executive Overview - Comparison** dashboard with one card showing:

| Metric    | Current | Prior | pct_change |
|-----------|---------|-------|------------|
| Revenue   | $125,000| $98,000 | +27.6%   |
| Orders    | 254     | 198   | +28.3%     |
| Spend     | $38,575 | $35,200 | +9.6%    |
| ROAS      | 3.2x    | 2.8x  | +14.3%     |
| Impressions| 2.8M   | 2.1M  | +33.3%     |
| Clicks    | 102,877 | 85,200 | +20.7%     |

---

## Step 2: Add the Period filter

1. Open **Executive Overview - Comparison** dashboard.
2. Click the **pencil** (Edit dashboard).
3. Click **+ Add a filter**.
4. Choose **Number**.
5. Configure:
   - **Label:** `Period (days)`
   - **Filter type:** Number
   - **Filter operator:** Equal to
   - **People can pick:** A single value
   - **Default value:** 7
6. Click **Done**.
7. Click the **Period (days)** filter pill.
8. In **Linked filters**, turn on the toggle for the comparison card.
9. When asked which variable to map to, choose **Period (days)** → `period_days`.
10. Click **Save**.

---

## Troubleshooting: "A number variable can only be connected to a number filter with Equal to operator"

This is a **known Metabase bug** (GitHub #44266) in versions before v0.50.7.

**Option A — Upgrade Metabase:** Update to v0.50.7 or later to fix the bug.

**Option B — Use Text filter (workaround):** The comparison card now uses a Text variable. Add a **Text** filter (not Number) and link it to `period_days`. Enter 7, 14, or 30 as the value.

**Option C — Fix existing card:** If you already created the dashboard with the old Number variable, run:

```powershell
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe fix_comparison_period_filter.py
```

Then remove the old Period filter, add a **Text** filter, and link it.

---

## Channel Performance dashboard

If you see this error on **Channel Performance** (Spend by channel over time, ROAS by channel, etc.):

- **If you ran `apply_date_range.py`:** Those cards only use Start date and End date. **Remove the Period filter** — it is not used by those cards.
- **If you ran `apply_option_b.py`:** The `period` variable is **Text** (Day|Week|Month). Use a **Category** or **Text** filter with options Day, Week, Month — **not** a Number filter.

---

## Usage

- **7** = Last 7 days vs previous 7 days
- **30** = Last 30 days vs previous 30 days
- **14** = Last 14 days vs previous 14 days

Change the filter value to compare different period lengths.
