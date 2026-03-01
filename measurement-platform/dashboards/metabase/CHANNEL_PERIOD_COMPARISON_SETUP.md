# Channel Performance: Period Comparison (4 Date Filters)

Updates Channel Performance cards to compare two date ranges side-by-side with % change.

**Filters:**
- **Start date** + **End date** = primary period
- **Comparison start date** + **Comparison end date** = comparison period

Each card shows metrics for both periods and a **pct_change** column.

---

## Step 1: Run the script

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
$env:METABASE_EMAIL = "your-email"
$env:METABASE_PASSWORD = "your-password"
python apply_channel_period_comparison.py
```

This updates all 4 Channel Performance cards to use the new comparison logic.

---

## Step 2: Add the 4 date filters

1. Open **Channel Performance** dashboard.
2. Click the **pencil** (Edit dashboard).
3. Remove any existing Period filter (if present).
4. Add **4 filters** (Date type, Single date):

| Filter label           | Maps to variable        |
|------------------------|-------------------------|
| Start date             | report_date_start       |
| End date               | report_date_end         |
| Comparison start date  | comparison_date_start   |
| Comparison end date    | comparison_date_end     |

For each filter:
- **Filter type:** Date picker
- **Filter operator:** Single date
- **Default value:** (optional) Set Start/End to your primary range, Comparison start/end to your comparison range

---

## Step 3: Link all 4 filters to all 4 cards

1. Click **Start date** filter pill → turn on toggle for all 4 cards → map to **Start date** (report_date_start).
2. Click **End date** filter pill → turn on toggle for all 4 cards → map to **End date** (report_date_end).
3. Click **Comparison start date** filter pill → turn on toggle for all 4 cards → map to **Comparison start date** (comparison_date_start).
4. Click **Comparison end date** filter pill → turn on toggle for all 4 cards → map to **Comparison end date** (comparison_date_end).
5. Click **Save**.

---

## Step 4: Set default values (optional)

If you leave filters empty, the cards use:
- **Primary period:** Last 30 days (CURRENT_DATE - 30 to CURRENT_DATE)
- **Comparison period:** Prior 30 days (CURRENT_DATE - 60 to CURRENT_DATE - 31)

To avoid "missing required parameters," set default dates on each filter or pick dates when viewing.

---

## Card output

| Card                         | Columns                                                                 |
|------------------------------|-------------------------------------------------------------------------|
| Spend by channel over time   | channel, period_spend, comparison_spend, pct_change                    |
| ROAS by channel              | channel, period_roas, comparison_roas, pct_change                       |
| Impressions and clicks       | channel, period_impressions, comparison_impressions, impressions_pct_change, period_clicks, comparison_clicks, clicks_pct_change |
| Spend share by channel       | channel, period_spend, comparison_spend, pct_change                    |
