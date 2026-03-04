# Client Performance Template dashboard setup

This guide creates one reusable Metabase dashboard template with:

- Executive / blended KPI trend cards
- Customer metrics trend cards
- Correlation charts
- Funnel views
- Platform metric pods (Meta, Google, TikTok)
- Supporting views
- GeoLift experiment snapshot

## 1) Prerequisites

- Metabase is running.
- A warehouse database is already connected in Metabase.
- `requests` is installed for Python.

## 2) Optional environment variables

```bash
export METABASE_URL="http://localhost:3000"
export METABASE_EMAIL="your-admin-email"
export METABASE_PASSWORD="your-password"
```

Or use API key:

```bash
export METABASE_API_KEY="your-metabase-api-key"
```

Schema variables:

```bash
# default: public_marts
export MARTS_SCHEMA="public_marts"

# default: Client Performance Template
export METABASE_TEMPLATE_DASHBOARD_NAME="Client Performance Template"
```

## 3) Dry run (recommended first)

```bash
python create_client_template_dashboard.py --dry-run
```

This validates section/card generation without calling Metabase APIs.

## 4) Create the template dashboard

```bash
python create_client_template_dashboard.py
```

If the dashboard already exists, the script prints the URL and exits safely.

## 5) Add dashboard filters in Metabase UI

After creation, open the dashboard in edit mode and add:

- `Start date` (Date; map to `report_date_start`)
- `End date` (Date; map to `report_date_end`)
- Optional channel filter for channel-level cards

## Notes on metric readiness

Cards labeled `(pending model)` are intentionally included placeholders for metrics that are not yet available in current marts, such as:

- LTV / LTV:CAC
- New customer metrics
- Platform-attributed ROAS / cost per purchase
- Deep funnel and creative metrics (add-to-cart, checkout, frequency, hook ratio, hold rate)

This keeps the dashboard template complete today while making missing metrics explicit.
