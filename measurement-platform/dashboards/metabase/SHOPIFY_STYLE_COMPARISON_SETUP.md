# Shopify-style KPI comparison cards (Metabase)

This setup adds KPI cards that behave more like Shopify:

- Big KPI number
- Up/down percentage change
- Green for positive / red for negative (default trend behavior)
- Comparison presets driven by a dashboard filter

Comparison presets supported:

- `previous_period` (default): same-length period immediately before selected range
- `previous_month`: selected range shifted back 1 month
- `previous_quarter`: selected range shifted back 3 months
- `previous_year`: selected range shifted back 1 year

---

## 1) Run the script

From PowerShell:

```powershell
$Repo = "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform"
$Script = "$Repo\dashboards\metabase\add_shopify_style_kpi_cards.py"

Set-Location $Repo
$env:METABASE_URL = "http://localhost:3000"
$env:METABASE_API_KEY = "YOUR_API_KEY"

# Optional: target a different dashboard (default is "Executive Overview")
# $env:METABASE_TARGET_DASHBOARD = "Channel Performance"

py -3 $Script
```

The script creates/updates these cards:

- `KPI Revenue - Comparison`
- `KPI Orders - Comparison`
- `KPI Spend - Comparison`
- `KPI ROAS - Comparison`
- `KPI Clicks - Comparison`
- `KPI Impressions - Comparison`

---

## 2) Link dashboard filters

Open the target dashboard in Metabase and click **Edit**.

You need these three filters linked to the KPI comparison cards:

1. **Start date** (Single date) -> `report_date_start`
2. **End date** (Single date) -> `report_date_end`
3. **Comparison mode** (Text or Category) -> `comparison_mode`

For **Comparison mode**, use one of:

- `previous_period`
- `previous_month`
- `previous_quarter`
- `previous_year`

Set the default to `previous_period`.

Save the dashboard.

---

## 3) Verify behavior

1. Set Start date and End date.
2. Set Comparison mode to `previous_period`.
3. KPI cards should show:
   - current selected-range value
   - up/down percent vs comparison range
4. Switch mode to `previous_year` and confirm values recalculate.

---

## Notes

- Trend color direction can be reversed per card in visualization settings (useful for metrics where lower is better).
- If a comparison window has zero baseline value, Metabase may show limited comparison behavior.
- If you already have old comparison cards, you can keep them or remove them; this setup does not delete existing cards.
