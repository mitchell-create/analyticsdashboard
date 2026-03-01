# Metabase dashboard date filter (fix “single date option” / linking)

## What went wrong

If questions were edited to use a SQL variable like `WHERE report_date = {{Date}}`, Metabase treats `{{Date}}` as a **Single Date input**, not a real column filter. So:

- You get: *“A date variable in this card can only be connected to a time type with the single date option.”*
- The dashboard **Date** filter has no **Linked filters** tab and you can’t connect a proper date range.

## Recommended fix: Option A — No SQL variables

Use **Option A**: remove SQL variables and let Metabase apply the dashboard date filter to the date column.

### Apply Option A via script (recommended)

From the repo root, with Metabase running and env set:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
$env:METABASE_EMAIL = "your-admin@email.com"
$env:METABASE_PASSWORD = "your-password"
python fix_metabase_date_filter.py
```

This updates every Executive Overview and Channel Performance question to the canonical variable-free SQL. Then add a dashboard Date filter and link it to each card (see below).

### Or: Edit each question in Metabase manually

### 1. Edit each question in Metabase

For each card on **Executive Overview** and **Channel Performance**:

1. Open the question (click the card → Edit, or open from “Saved questions”).
2. If the SQL has something like:
   - `WHERE report_date = {{Date}}`
   - or `WHERE date = {{Date}}`
   remove that `WHERE` (and the variable) entirely.
3. Keep the rest of the query, e.g.:

   ```sql
   SELECT report_date AS date, channel, COALESCE(SUM(spend), 0) AS spend
   FROM public_marts.fact_spend_daily
   GROUP BY report_date, channel
   ORDER BY report_date, channel
   ```

   No `WHERE` clause. The query returns all dates; the dashboard filter will limit what’s shown.
4. Save the question.

### 2. Add and link the dashboard Date filter

See **Step-by-step guide** below.

After this, the dashboard Date filter applies to the date column and linking works.

---

## Step-by-step: Add and link the Date filter

Do this for **Executive Overview** and **Channel Performance** (and any other dashboard that uses date).

### Part A — Add the Date filter

1. Open Metabase and go to the dashboard (e.g. **Executive Overview**).
2. Click the **pencil** (Edit dashboard) so the dashboard is in edit mode.
3. In the top bar, click **+** (Add) or **Add a filter**.
4. In the “Add a filter or parameter” menu, choose **Date picker** (calendar icon, “Date range, specific date…”).
5. In the right panel:
   - **Label:** leave as “Date” or rename (e.g. “Report date”).
   - **Filter or parameter type:** **Date picker** (should already be set).
   - **Filter operator:** choose **Single date** or **Date range** (e.g. “Between” for a range).
   - **Default value (optional):** e.g. “Last 30 days” or “No default”.
6. Click **Done** (or **Add filter**). The **Date** filter pill appears at the top of the dashboard.
7. Do **Part B** to link it to cards, then **Save** the dashboard (top right).

### Part B — Link the filter to each card

1. With the dashboard still in **edit mode**, click the **Date** filter pill at the top.
2. In the right panel, look for:
   - A **Linked filters** tab, or  
   - A section like **“Which cards should this filter apply to?”** or **“Limit this filter’s choices”**.
3. If you see **Linked filters**:
   - Open the **Linked filters** tab.
   - You should see a list of dashboard cards. For each card you want to filter by date, **turn on** the toggle or check the box.
   - If Metabase asks which **field** to filter, choose the date column (e.g. **date** or **report_date**) for that question.
4. If you **don’t** see Linked filters on the Date filter:
   - **From the card:** Click one of the data cards (e.g. “Daily revenue”). Look for a **link** or **filter** icon on the card, or a “Link to dashboard filter” option. Choose the **Date** filter and map it to the **date** (or **report_date**) field. Repeat for each card.
5. Repeat for every card that has a date axis or date column (e.g. Daily revenue, Daily orders, Spend by date, Total spend by channel, ROAS, and on Channel Performance: Spend by channel over time, ROAS by channel, Impressions and clicks, Spend share by channel).
6. Click **Done** on the filter panel (if it’s open).
7. Click **Save** (top right) to save the dashboard.

### Part C — Test

1. Exit edit mode (or open the dashboard in view mode).
2. Change the **Date** filter (e.g. pick “Last 7 days” or a specific range).
3. All linked cards should update to show only data in that date range.

### Repeat for Channel Performance

1. Open the **Channel Performance** dashboard.
2. Follow **Part A** (add Date filter), **Part B** (link to each card), then **Save**.
3. Test with a date range.

---

## Alternative: Option B — Field filter in SQL

If you want to keep a filter inside the SQL:

1. In the question SQL, use a **field filter** variable, e.g.:
   - `WHERE {{report_date}}`
2. In the variable configuration for `report_date`:
   - **Type:** Field Filter  
   - **Field:** e.g. `fact_spend_daily.report_date` (pick the table and date column)
3. Then the dashboard Date filter can be linked to this variable.

Option A is simpler and matches how `create_mvp_dashboards.py` builds questions (no variables).

---

## Date range option (recommended)

**Use `apply_date_range.py`** for a real date range (From X to Y). See **METABASE_DATE_RANGE_SETUP.md** for full instructions.

---

## Previous setup (Option B — single date + Period)

**What we had before:**  
Executive Overview and Channel Performance use **Option B** via `apply_option_b.py` with a **workaround** because Metabase’s Field Filter (dimension) on native SQL causes “invalid reference to FROM-clause” on single-table questions. So we use:

- **Date** filter = single date (dashboard “Single date”).
- **Period** filter = text “Day”, “Week”, or “Month” to expand that date into a day, ISO week (Mon–Sun), or calendar month.

So users pick one date + Period, not a true “from–to” range.

**Future improvement (to revisit):**  
We want to support a **real date range** (e.g. “From 2025-01-01 to 2025-01-31” or “Last 30 days”) so users can pick start and end directly instead of single date + Day/Week/Month. Options to explore later:

1. **Metabase upgrade or config:** See if a newer Metabase (or different filter/variable type) allows a dashboard date-range filter to link to native SQL without the dimension expansion bug.
2. **Two basic date variables:** e.g. `report_date_start` and `report_date_end` with SQL `WHERE report_date >= {{report_date_start}} AND report_date <= {{report_date_end}}`. This previously failed because the dashboard “All options” (range) filter couldn’t link to basic date variables (“single date option” error); worth re-testing after Metabase or UI changes.
3. **Different question type:** Build the same metrics as Metabase “query builder” (non–native SQL) questions so the dashboard date-range filter links correctly, then mirror the SQL logic.

When revisiting, search this doc for “Future improvement” and update this section with what was tried and what worked.
