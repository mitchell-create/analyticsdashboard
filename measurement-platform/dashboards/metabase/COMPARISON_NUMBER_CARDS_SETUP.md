# Adding Comparison Number Cards to Channel Performance

Adds 4 Number cards to Channel Performance dashboard:

| Card | Columns |
|------|---------|
| Total Spend | spend, change_pct |
| Total Impressions | impressions, change_pct |
| Total Clicks | clicks, change_pct |
| ROAS | roas, change_pct |

Each card shows the current period value and the % change vs the comparison period.

---

## Step 1: Make sure Metabase is running

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard"
java -jar metabase.jar
```

Wait for `http://localhost:3000` to be available.

---

## Step 2: Run the script

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
$env:METABASE_EMAIL = "mitchell@nexocore.ca"
$env:METABASE_PASSWORD = '@Emmajake123'
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe add_comparison_number_cards.py
```

This adds 4 new Number cards to the bottom of the Channel Performance dashboard.

---

## Step 3: View the dashboard

Open `http://localhost:3000` → Dashboards → **Channel Performance**

You should see 4 new cards at the bottom, each showing:
- **Column 1:** Current period metric (e.g., spend: 15,234.56)
- **Column 2:** % change (e.g., change_pct: +12.3 or -5.7)

---

## Step 4: Set the date filters (required)

The cards use the same 4 date filters as the rest of the dashboard:
- **Start date** + **End date** (primary period)
- **Comparison start date** + **Comparison end date** (comparison period)

**You must set all 4 filters** for the Number cards to work. For example:
- Start date: Jan 15, 2026
- End date: Feb 4, 2026 (21 days)
- Comparison start date: Dec 25, 2025
- Comparison end date: Jan 14, 2026 (21 days)

This compares the current 21 days vs the previous 21 days.

---

## Result

Each card will show a clean 1-row table:

| spend | change_pct |
|-------|------------|
| 21,234.56 | +15.7% |

The main value is on the left, % change on the right.
