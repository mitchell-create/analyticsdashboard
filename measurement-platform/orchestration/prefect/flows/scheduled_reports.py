"""
scheduled_reports.py — Automated Chellegum performance reports posted to Slack.

Schedules:
  - 1st of every month: previous full month of data
  - 14th of every month: last 14 days of data

Report format:
  Per-platform breakdown (spend, purchase value, ROAS):
    - Meta
    - TikTok Ads (web)
    - GMV Max (TikTok Shop)
  Combined totals: total spend, total purchase value, total ROAS
"""

import os
from datetime import date, timedelta

from prefect import flow, task
from prefect.logging import get_run_logger

# Chubblegum Slack channel
CHUBBLEGUM_CHANNEL_ID = "C0AEXRYPA9Y"


def _post_slack_message(message: str, channel: str | None = None) -> None:
    try:
        from slack_sdk import WebClient

        token = os.environ.get("SLACK_BOT_TOKEN")
        ch = channel or CHUBBLEGUM_CHANNEL_ID
        if token and ch:
            client = WebClient(token=token)
            client.chat_postMessage(channel=ch, text=message)
    except Exception as e:
        print(f"Slack message failed: {e}")


def _get_pg_connection():
    """Direct PostgreSQL connection for report queries."""
    import psycopg2

    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        return None
    return psycopg2.connect(db_url)


def _fmt_currency(val) -> str:
    if val is None:
        return "$0.00"
    num = float(val)
    if num >= 1_000_000:
        return f"${num:,.0f}"
    return f"${num:,.2f}"


def _fmt_roas(val) -> str:
    if val is None or float(val) == 0:
        return "0.00x"
    return f"{float(val):.2f}x"


def _compute_period(report_date: date) -> tuple[date, date, str]:
    """Determine the reporting period based on the current date.

    On the 1st: report on the full previous month.
    On the 14th (or any other day): report on the last 14 days.
    """
    if report_date.day == 1:
        end_date = report_date - timedelta(days=1)
        start_date = end_date.replace(day=1)
        label = f"{start_date.strftime('%B %Y')} (Full Month)"
    else:
        end_date = report_date - timedelta(days=1)
        start_date = report_date - timedelta(days=14)
        label = f"{start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')} (Last 14 Days)"
    return start_date, end_date, label


@task
def fetch_report_data(start_date: date, end_date: date) -> dict:
    """Query Chellegum metrics for the given date range.

    Returns dict with keys: meta, tiktok_ads, gmv_max.
    Each contains: spend, purchase_value, roas.
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

        # --- Meta: spend, purchase_value, ROAS ---
        cur.execute("""
            SELECT
                COALESCE(SUM(spend), 0) AS spend,
                COALESCE(SUM(purchase_value), 0) AS purchase_value,
                CASE WHEN SUM(spend) > 0
                     THEN SUM(purchase_value) / SUM(spend)
                     ELSE 0 END AS roas
            FROM public_marts.fact_spend_daily
            WHERE channel = 'meta'
              AND report_date >= %s AND report_date <= %s
        """, (start_str, end_str))
        row = cur.fetchone()
        results["meta"] = {
            "spend": float(row[0]) if row else 0,
            "purchase_value": float(row[1]) if row else 0,
            "roas": float(row[2]) if row else 0,
        }

        # --- TikTok Ads (web): spend, purchase_value, ROAS ---
        cur.execute("""
            SELECT
                COALESCE(SUM(spend), 0) AS spend,
                COALESCE(SUM(purchase_value), 0) AS purchase_value,
                CASE WHEN SUM(spend) > 0
                     THEN SUM(purchase_value) / SUM(spend)
                     ELSE 0 END AS roas
            FROM public_marts.fact_spend_daily
            WHERE channel = 'tiktok'
              AND report_date >= %s AND report_date <= %s
        """, (start_str, end_str))
        row = cur.fetchone()
        results["tiktok_ads"] = {
            "spend": float(row[0]) if row else 0,
            "purchase_value": float(row[1]) if row else 0,
            "roas": float(row[2]) if row else 0,
        }

        # --- GMV Max (Chellegum / TikTok Shop): spend, purchase_value, ROAS ---
        cur.execute("""
            SELECT
                COALESCE(SUM(cost), 0) AS spend,
                COALESCE(SUM(gross_revenue), 0) AS purchase_value,
                CASE WHEN SUM(cost) > 0
                     THEN SUM(gross_revenue) / SUM(cost)
                     ELSE 0 END AS roas
            FROM public_marts.fact_tiktok_gmv_max_daily
            WHERE client_slug = 'chubble'
              AND report_date >= %s AND report_date <= %s
        """, (start_str, end_str))
        row = cur.fetchone()
        results["gmv_max"] = {
            "spend": float(row[0]) if row else 0,
            "purchase_value": float(row[1]) if row else 0,
            "roas": float(row[2]) if row else 0,
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
        return ":warning: *Chellegum Report*\nNo data available for this period."

    meta = data.get("meta", {})
    tiktok = data.get("tiktok_ads", {})
    gmv = data.get("gmv_max", {})

    # Combined totals
    total_spend = meta.get("spend", 0) + tiktok.get("spend", 0) + gmv.get("spend", 0)
    total_pv = meta.get("purchase_value", 0) + tiktok.get("purchase_value", 0) + gmv.get("purchase_value", 0)
    total_roas = total_pv / total_spend if total_spend > 0 else 0

    lines = [
        f":bar_chart: *Chellegum Performance Report*",
        f"*{period_label}*",
        "",
        "*Meta*",
        f"  Spend:           {_fmt_currency(meta.get('spend'))}",
        f"  Purchase Value:  {_fmt_currency(meta.get('purchase_value'))}",
        f"  ROAS:            {_fmt_roas(meta.get('roas'))}",
        "",
        "*TikTok Ads (Web)*",
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
        "*TOTALS (All Platforms)*",
        f"  Total Spend:           {_fmt_currency(total_spend)}",
        f"  Total Purchase Value:  {_fmt_currency(total_pv)}",
        f"  Total ROAS:            {_fmt_roas(total_roas)}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


@flow(name="chellegum_scheduled_report", description="Chellegum bi-monthly performance report (1st and 14th)")
def chellegum_scheduled_report() -> None:
    """Generate and post the Chellegum performance report to Slack.

    Runs on the 1st (previous month) and 14th (last 14 days) of each month.
    Posts to the #chubblegum Slack channel (C0AEXRYPA9Y).
    """
    logger = get_run_logger()
    today = date.today()

    start_date, end_date, period_label = _compute_period(today)
    logger.info(f"Generating Chellegum report: {period_label} ({start_date} to {end_date})")

    data = fetch_report_data.submit(start_date, end_date).result()

    if not data:
        logger.warning("No data returned; posting warning to Slack")
        _post_slack_message(
            ":warning: *Chellegum Report*\n"
            f"Period: {period_label}\n"
            "Could not fetch report data. Check database connection."
        )
        return

    report = format_report.submit(data, period_label).result()
    logger.info("Report formatted, posting to Slack")

    _post_slack_message(report)
    logger.info("Chellegum report posted to #chubblegum")


if __name__ == "__main__":
    chellegum_scheduled_report()
