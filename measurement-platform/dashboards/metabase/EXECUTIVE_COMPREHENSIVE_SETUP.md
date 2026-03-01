# Executive Overview - Comprehensive Dashboard Setup

Creates an executive-friendly dashboard with all key metrics:

## Dashboard Layout

**Row 1: Executive KPIs**
- Total Ad Spend
- Total Shopify Revenue  
- MER (Marketing Efficiency Ratio)
- Net Ad Profit

**Row 2: Efficiency KPIs**
- Total Shopify Orders
- CPA (Cost Per Purchase)
- AOV (Average Order Value)
- Blended CAC

**Row 3: Customer KPIs** *(placeholders for now)*
- New Customers
- Returning Customers
- LTV (Lifetime Value)
- LTV:CAC Ratio

**Row 4: Trend Chart**
- Daily Spend vs Revenue (line chart)

**Row 5: Spend Breakdown**
- Spend Share by Platform (pie chart)

**Row 6: Supporting Metrics**
- Total Impressions
- Total Clicks
- Blended CPC
- Blended CPM
- CVR (Conversion Rate)

---

## Step 1: Make sure Metabase is running

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard"
java -jar metabase.jar
```

---

## Step 2: Run the script

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
$env:METABASE_EMAIL = "mitchell@nexocore.ca"
$env:METABASE_PASSWORD = '@Emmajake123'
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe create_executive_comprehensive_dashboard.py
```

---

## Step 3: Add date filters

1. Open the new dashboard in Metabase
2. Click **Edit dashboard** (pencil icon)
3. Click **+ Add a filter** → **Date picker**
4. Configure:
   - **Label:** Start date
   - **Filter operator:** Single date
5. Click **Done**
6. Add another filter for **End date**
7. Click the **Start date** filter pill
8. Turn on the toggle for all cards and map to **Start date** variable
9. Click the **End date** filter pill
10. Turn on the toggle for all cards and map to **End date** variable
11. Click **Save**

---

## Result

You'll have a comprehensive executive dashboard showing:
- All key performance metrics as Number cards
- Daily trend of spend vs revenue
- Platform spend allocation

**Set the date filters to view metrics for any date range.**

---

## Notes

- **New Customers, Returning Customers, LTV, LTV:CAC** are placeholders (show 0) until we add customer cohort tracking
- **CAC calculation** currently uses order count; update to use actual new customer count when available
- All other metrics are live and calculated from your data
