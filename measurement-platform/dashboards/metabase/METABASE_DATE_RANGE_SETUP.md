# Metabase Date Range Filter Setup

This guide sets up a **real date range** filter (From X to Y) for Executive Overview and Channel Performance dashboards, replacing the single-date + Period workaround.

---

## Step 1: Run the script

With Metabase running and your credentials set:

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\dashboards\metabase"
$env:METABASE_EMAIL = "your-admin@email.com"
$env:METABASE_PASSWORD = "your-password"
C:\Users\ReadyPlayerOne\AppData\Local\Programs\Python\Python312\python.exe apply_date_range.py
```

This updates all date-based cards to use `report_date_start` and `report_date_end` variables.

---

## Step 2: Add dashboard filters (Executive Overview)

1. Open **Executive Overview** dashboard.
2. Click the **pencil** (Edit dashboard).
3. Click **+ Add a filter**.
4. Choose **Date** (calendar icon).
5. Configure the first filter:
   - **Label:** `Start date`
   - **Filter type:** Date
   - **Filter operator:** Single date
   - **Default value:** Relative date → Past → 30 → days (so it defaults to 30 days ago)
6. Click **Done**.
7. Add a second filter:
   - **Label:** `End date`
   - **Filter type:** Date
   - **Filter operator:** Single date
   - **Default value:** Relative date → Today
8. Click **Save** (top right).


---

## Step 3: Link filters to each card

1. With the dashboard in **edit mode**, click the **Start date** filter pill.
2. In the right panel, find **Linked filters** or **Which cards should this filter apply to?**
3. For each card (Daily revenue, Daily orders, Spend by date, etc.):
   - Turn on the toggle for that card.
   - When asked which **variable** to map to, choose **Start date** (report_date_start).
4. Click the **End date** filter pill.
5. Link it to the same cards, mapping to **End date** (report_date_end).
6. Click **Save**.

---

## Step 4: Set filter defaults (optional)

1. Click **Start date** filter → set default to **Relative date** → **Past** → **30** → **days**.
2. Click **End date** filter → set default to **Relative date** → **Today**.
3. Save.

---

## Step 5: Repeat for Channel Performance and Email & Klaviyo

1. Open **Channel Performance** dashboard.
2. Add the same two filters (Start date, End date).
3. Link both to all cards on that dashboard.
4. Save.
5. Open **Email & Klaviyo** dashboard and do the same for its date-based cards.

---

## Usage

- Pick **Start date** and **End date** to define your range.
- Use **Last 7 days**, **Last 30 days**, or **Custom range** if your Metabase version supports it on the date filter.
- All linked cards will filter to that date range.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Variable not found" when linking | Ensure the script ran successfully. Re-run `apply_date_range.py`. |
| Cards show no data | Check that Start date ≤ End date and your data exists in that range. |
| Filter doesn't apply | Verify both Start date and End date are linked to each card. |
| Only one bound seems to apply (or range behaves oddly) | Re-run `apply_date_range.py` from this repo version. Older SQL used inline `--` defaults that could comment out the rest of a date predicate once a variable was set. |
