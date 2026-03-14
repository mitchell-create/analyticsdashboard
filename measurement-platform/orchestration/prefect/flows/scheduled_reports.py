"""
scheduled_reports.py — Automated Chubblegum performance reports posted to Slack.

Schedules:
  - 1st of every month: previous full month of data
  - 14th of every month: last 14 days of data

Reports include:
  1. Combined totals: total spend, combined ROAS, purchase value (all platforms)
  2. Breakdown by platform:
     - Regular TikTok Ads: spend, ROAS, purchase value
     - GMV Max: spend, ROAS, purchase value
     - Meta: spend, ROAS, purchase value
"""

import os
from datetime import date, timedelta
from decimal import Decimal

from prefect import flow, task
from prefect.logging import get_run_logger


def _post_slack_message(message: str, channel: str | None = None) -> None:
    try:
        from slack_sdk import WebClient

        token = os.environ.get("SLACK_BOT_TOKEN")
        ch = channel or os.environ.get("SLACK_REPORT_CHANNEL_ID") or os.environ.get("SLACK_ALERT_CHANNEL_ID")
        if token and ch:
            client = WebClient(token=token)
            client.chat_postMessage(channel=ch, text=message)
    except Exception as e:
        print(f"Slack message failed: {e}")


def _get_supabase():
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def _get_pg_connection():
    """Direct PostgreSQL connection for queries that need SQL JOINs."""
    import psycopg2

    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        return None
    return psycopg2.connect(db_url)


def _fmt_currency(val) -> str:
    """Format a number as currency."""
    if val is None:
        return "$0.00"
    num = float(val)
    if num >= 1_000_000:
        return f"${num:,.0f}"
    return f"${num:,.2f}"


def _fmt_roas(val) -> str:
    """Format ROAS value."""
    if val is None or float(val) == 0:
        return "0.00x"
    return f"{float(val):.2f}x"


def _fmt_int(val) -> str:
    """Format integer with commas."""
    if val is None:
        return "0"
    return f"{int(val):,}"


def _compute_period(report_date: date) -> tuple[date, date, str]:
    """Determine the reporting period based on the current date.

    On the 1st: report on the full previous month.
    On the 14th: report on the last 14 days.
    Otherwise (manual run): last 14 days.
    """
    if report_date.day == 1:
        # Previous full month
        end_date = report_date - timedelta(days=1)  # last day of prev month
        start_date = end_date.replace(day=1)  # first day of prev month
        label = f"{start_date.strftime('%B %Y')} (Full Month)"
    else:
        # Last 14 days
        end_date = report_date - timedelta(days=1)
        start_date = report_date - timedelta(days=14)
        label = f"{start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')} (Last 14 Days)"
    return start_date, end_date, label


@task
def fetch_report_data(start_date: date, end_date: date) -> dict:
    """Query all Chubblegum metrics for the given date range.

    Returns dict with keys: meta, tiktok_ads, gmv_max, combined.
    Each contains: spend, purchase_value, roas, orders.
    """
    logger = get_run_logger()
    conn = _get_pg_connection()
    if not conn:
        logger.warning("No SUPABASE_DB_URL set; cannot fetch report data")
        return {}

    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    results = {}
    try:
        cur = conn.cursor()

        # --- Meta spend + purchase value ---
        # Meta spend from fact_spend_daily, purchase value from fact_kpi_daily
        # attributed to Meta's date range
        cur.execute("""
            SELECT
                COALESCE(SUM(spend), 0) AS spend
            FROM public_marts.fact_spend_daily
            WHERE channel = 'meta'
              AND report_date >= %s AND report_date <= %s
        """, (start_str, end_str))
        row = cur.fetchone()
        meta_spend = float(row[0]) if row else 0

        # Meta purchase value: we use Shopify revenue as the purchase value
        # attributed proportionally, or total if Meta is the only paid channel.
        # For now, use total Shopify revenue as combined purchase value.
        cur.execute("""
            SELECT
                COALESCE(SUM(revenue), 0) AS purchase_value,
                COALESCE(SUM(orders), 0) AS orders
            FROM public_marts.fact_kpi_daily
            WHERE report_date >= %s AND report_date <= %s
        """, (start_str, end_str))
        row = cur.fetchone()
        total_purchase_value = float(row[0]) if row else 0
        total_orders = int(row[1]) if row else 0

        # For Meta purchase value, we'll use total Shopify revenue
        # (standard attribution — Shopify is the source of truth for purchases)
        meta_purchase_value = total_purchase_value
        meta_roas = meta_purchase_value / meta_spend if meta_spend > 0 else 0

        results["meta"] = {
            "spend": meta_spend,
            "purchase_value": meta_purchase_value,
            "roas": meta_roas,
        }

        # --- Regular TikTok Ads ---
        cur.execute("""
            SELECT
                COALESCE(SUM(spend), 0) AS spend
            FROM public_marts.fact_spend_daily
            WHERE channel = 'tiktok'
              AND report_date >= %s AND report_date <= %s
        """, (start_str, end_str))
        row = cur.fetchone()
        tiktok_spend = float(row[0]) if row else 0

        # TikTok Ads doesn't have its own purchase value in fact_spend_daily,
        # so we report spend and note ROAS requires attribution
        results["tiktok_ads"] = {
            "spend": tiktok_spend,
            "purchase_value": 0,
            "roas": 0,
        }

        # --- GMV Max (Chellegum only) ---
        cur.execute("""
            SELECT
                COALESCE(SUM(cost), 0) AS spend,
                COALESCE(SUM(gross_revenue), 0) AS purchase_value,
                COALESCE(SUM(orders), 0) AS orders,
                CASE WHEN SUM(cost) > 0
                     THEN SUM(gross_revenue) / SUM(cost)
                     ELSE 0 END AS roas
            FROM public_marts.fact_tiktok_gmv_max_daily
            WHERE client_slug = 'chubble'
              AND report_date >= %s AND report_date <= %s
        """, (start_str, end_str))
        row = cur.fetchone()
        gmv_spend = float(row[0]) if row else 0
        gmv_pv = float(row[1]) if row else 0
        gmv_orders = int(row[2]) if row else 0
        gmv_roas = float(row[3]) if row else 0

        results["gmv_max"] = {
            "spend": gmv_spend,
            "purchase_value": gmv_pv,
            "orders": gmv_orders,
            "roas": gmv_roas,
        }

        # --- Combined totals ---
        combined_spend = meta_spend + tiktok_spend + gmv_spend
        combined_pv = total_purchase_value + gmv_pv  # Shopify revenue + GMV Max revenue
        combined_roas = combined_pv / combined_spend if combined_spend > 0 else 0

        results["combined"] = {
            "spend": combined_spend,
            "purchase_value": combined_pv,
            "roas": combined_roas,
        }

        cur.close()
    except Exception as e:
        logger.error(f"Report query failed: {e}")
    finally:
        conn.close()

    return results


@task
def format_report(data: dict, period_label: str) -> str:
    """Format the report data into a Slack message."""
    if not data:
        return ":warning: *Chubblegum Report*\nNo data available for this period."

    combined = data.get("combined", {})
    meta = data.get("meta", {})
    tiktok = data.get("tiktok_ads", {})
    gmv = data.get("gmv_max", {})

    lines = [
        f":chart_with_upwards_trend: *Chubblegum Performance Report*",
        f"*{period_label}*",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "*COMBINED TOTALS (All Platforms)*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  Total Spend:          {_fmt_currency(combined.get('spend'))}",
        f"  Total Purchase Value:  {_fmt_currency(combined.get('purchase_value'))}",
        f"  Combined ROAS:        {_fmt_roas(combined.get('roas'))}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "*BREAKDOWN BY PLATFORM*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "*Meta*",
        f"  Spend:           {_fmt_currency(meta.get('spend'))}",
        f"  Purchase Value:  {_fmt_currency(meta.get('purchase_value'))}",
        f"  ROAS:            {_fmt_roas(meta.get('roas'))}",
        "",
        "*TikTok Ads*",
        f"  Spend:           {_fmt_currency(tiktok.get('spend'))}",
        f"  Purchase Value:  {_fmt_currency(tiktok.get('purchase_value'))}",
        f"  ROAS:            {_fmt_roas(tiktok.get('roas'))}",
        "",
        "*GMV Max (TikTok Shop)*",
        f"  Spend:           {_fmt_currency(gmv.get('spend'))}",
        f"  Purchase Value:  {_fmt_currency(gmv.get('purchase_value'))}",
        f"  ROAS:            {_fmt_roas(gmv.get('roas'))}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


@flow(name="chubblegum_scheduled_report", description="Chubblegum bi-monthly performance report (1st and 14th)")
def chubblegum_scheduled_report() -> None:
    """Generate and post the Chubblegum performance report to Slack.

    Runs on the 1st (previous month) and 14th (last 14 days) of each month.
    """
    logger = get_run_logger()
    today = date.today()

    start_date, end_date, period_label = _compute_period(today)
    logger.info(f"Generating Chubblegum report: {period_label} ({start_date} to {end_date})")

    data = fetch_report_data.submit(start_date, end_date).result()

    if not data:
        logger.warning("No data returned; posting warning to Slack")
        _post_slack_message(
            ":warning: *Chubblegum Report*\n"
            f"Period: {period_label}\n"
            "Could not fetch report data. Check database connection."
        )
        return

    report = format_report.submit(data, period_label).result()
    logger.info("Report formatted, posting to Slack")

    _post_slack_message(report)
    logger.info("Chubblegum report posted to Slack")


if __name__ == "__main__":
    chubblegum_scheduled_report()
