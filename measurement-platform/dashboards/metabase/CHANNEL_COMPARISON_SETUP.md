# Channel Performance: Period Comparison

Adds a comparison card to your **Channel Performance** dashboard showing each channel's spend, impressions, and clicks for the current period vs the previous period with % change.

---

## Step 1: Run the script

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
$env:METABASE_EMAIL = "your-email"
$env:METABASE_PASSWORD = "your-password"
python add_channel_comparison_card.py
```

This adds a new card **"Channel comparison: Current vs Prior period"** to your existing Channel Performance dashboard.

---

## Step 2: Add the Period (days) filter

1. Open **Channel Performance** dashboard.
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

---

## Step 3: Link the filter to the comparison card only

1. Click the **Period (days)** filter pill.
2. Turn on the toggle **only** for the card **"Channel comparison: Current vs Prior period"**.
3. Map to **Period (days)** → `period_days`.
4. Leave the other cards (Spend by channel over time, ROAS by channel, etc.) **unlinked** — they use Start date and End date.
5. Click **Save**.

---

## Usage

- **7** = Last 7 days vs previous 7 days
- **14** = Last 14 days vs previous 14 days  
- **30** = Last 30 days vs previous 30 days

The comparison card shows: channel, cur_spend, prior_spend, spend_pct_change, cur_impressions, prior_impressions, impressions_pct_change, cur_clicks, prior_clicks, clicks_pct_change.
