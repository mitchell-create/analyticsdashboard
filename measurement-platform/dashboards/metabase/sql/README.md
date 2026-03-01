# Metabase dashboard SQL queries

Use these SQL files to create questions in Metabase manually, or as reference for the API script.

## Folder structure

| Folder | Dashboard | Charts |
|--------|-----------|--------|
| `01_executive_overview/` | Executive Overview | Daily revenue, Daily orders, Spend by date, Total spend by channel, ROAS |
| `02_channel_performance/` | Channel Performance | Spend by channel over time, ROAS by channel, Impressions/clicks, Spend share (pie) |
| `03_email_klaviyo/` | Email & Klaviyo | Email sends by day, Opens/clicks by day, Campaigns summary |
| `04_experiment_results/` | Experiment Results | Experiments list, Lift over time, Latest lift summary |

## Manual setup

1. In Metabase, create a new dashboard (e.g. "Executive Overview").
2. Add a question → **Native query**.
3. Copy the SQL from the `.sql` file.
4. Run the query and choose the visualization (Line, Bar, Pie, Table).
5. Save and add to the dashboard.
6. Repeat for each chart.

## Chart types

- **Line:** daily_revenue, daily_orders, spend_by_date, spend_by_channel_over_time, impressions_clicks_by_channel, email_sends_by_day, opens_clicks_by_day, lift_over_time
- **Bar:** total_spend_by_channel
- **Pie:** spend_share_by_channel
- **Table:** roas, roas_by_channel, campaigns_summary, experiments_list, latest_lift_summary
