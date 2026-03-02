# KPI Number Cards with Automatic Previous-Period Comparison

Creates number cards that show a **single large number** for your selected date range, with an **↑/↓ arrow and % change** vs the previous period — exactly like Shopify analytics.

---

## What you get

### Number cards (6 KPI cards)

| Card | Metric | Example |
|------|--------|---------|
| KPI: Total Spend | Sum of ad spend | **$15,234** ↑ 12.3% |
| KPI: Total Revenue | Sum of Shopify revenue | **$52,100** ↓ 3.1% |
| KPI: ROAS | Revenue ÷ Spend | **3.42** ↑ 8.7% |
| KPI: Total Orders | Sum of orders | **412** ↑ 5.2% |
| KPI: CPA | Spend ÷ Orders | **$36.95** ↓ 2.1% |
| KPI: AOV | Revenue ÷ Orders | **$126.46** ↑ 1.4% |

Each card is a **big number with a comparison arrow**. No tables, no individual dates — just the aggregated KPI for the period you selected, with automatic comparison.

### Comparison line charts (2 overlay charts)

- **Spend: Current vs Previous Period** — daily spend for both periods overlaid on the same date axis
- **Revenue: Current vs Previous Period** — daily revenue for both periods overlaid

---

## How the previous period works

The previous period is **automatically calculated** — same number of days, immediately before your start date.

| You select | Period length | Previous period (auto) |
|------------|---------------|----------------------|
| Feb 10 – Feb 26 | 17 days | Jan 24 – Feb 9 |
| Feb 1 – Feb 28 | 28 days | Jan 4 – Jan 31 |
| Jan 1 – Mar 31 | 90 days | Oct 3 – Dec 31 |

You only need **2 date filters** (Start date, End date). No manual comparison dates required.

---

## Setup

### Step 1: Make sure Metabase is running

```bash
java -jar metabase.jar
# Wait for http://localhost:3000
```

### Step 2: Run the script

**PowerShell (Windows):**

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
$env:METABASE_EMAIL = "mitchell@nexocore.ca"
$env:METABASE_PASSWORD = "@Emmajake123"

# Creates a new "KPI Summary" dashboard with all cards
python create_kpi_number_cards.py

# Or add cards to an existing dashboard:
python create_kpi_number_cards.py --dashboard "Executive Overview"
```

**Bash / macOS / Linux:**

```bash
cd measurement-platform/dashboards/metabase
export METABASE_EMAIL="your-admin-email"
export METABASE_PASSWORD="your-password"
python create_kpi_number_cards.py
```

> **Note:** On Windows PowerShell, use `$env:VAR = "value"` instead of `export VAR="value"`.

### Step 3: Add date filters to the dashboard

1. Open the dashboard in Metabase.
2. Click the **pencil icon** (Edit) → **Filter icon** → add 2 filters:
   - **Date picker** → **Single date** → name it **Start date**
   - **Date picker** → **Single date** → name it **End date**
3. For **each filter**, click the gear icon and wire it to **every card**:
   - **Start date** → `report_date_start` (on all 8 cards)
   - **End date** → `report_date_end` (on all 8 cards)
4. **Save** the dashboard.

### Step 4: Use it

1. Set **Start date** = Feb 10, 2026
2. Set **End date** = Feb 26, 2026
3. Each KPI card now shows:
   - The aggregated value for Feb 10–26 (big number)
   - ↑/↓ % change vs Jan 24 – Feb 9 (arrow in the corner)
4. The line charts show daily spend/revenue for both periods overlaid.

---

## How it works (technical)

### Why the old cards showed a table instead of a number

The old comparison cards (`add_comparison_number_cards.py`) used `display: "scalar"` with SQL that returned two columns: `value` and `change_pct`. Metabase's `scalar` display only renders the first cell — the `change_pct` column was invisible. When Metabase couldn't render it properly, it fell back to a table view showing individual dates.

### The fix: smartscalar with 2-row pattern

The new cards use `display: "smartscalar"` (called "Trend" in the Metabase UI). The SQL returns **exactly 2 rows**:

| date (row) | metric |
|------------|--------|
| Jan 24 (previous period end) | 8.50 |
| Feb 26 (current period end) | 10.20 |

Metabase's smartscalar automatically:
1. Displays the **latest row** (10.20) as a big number
2. Computes **% change** vs the previous row (8.50 → 10.20 = +20%)
3. Shows an **↑ arrow** in green (or ↓ in red if the value decreased)

### Comparison line charts

The overlay charts shift previous-period dates forward by `period_days` so both periods align on the same x-axis. This lets you visually compare daily trends side by side.

---

## Removing old comparison cards

If you previously ran `add_comparison_number_cards.py`, you may want to remove those old cards:

1. Open the dashboard in Metabase.
2. Click **Edit** (pencil icon).
3. Find the old cards (named "Total Spend", "Total Impressions", "Total Clicks", "ROAS" — the ones showing as tables with `change_pct` column).
4. Click the **×** on each old card to remove it.
5. Save the dashboard.

The new cards are named with a "KPI:" prefix (e.g., "KPI: ROAS") to distinguish them.
