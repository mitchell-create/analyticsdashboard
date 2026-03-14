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

import json
import os
import subprocess
from datetime import date, timedelta

from prefect import flow, task
from prefect.logging import get_run_logger

# Chubblegum Slack channel
CHUBBLEGUM_CHANNEL_ID = "C0AEXRYPA9Y"

# Supabase config
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://xopsomagbnsnadxxhzhx.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


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


def _supabase_query(table: str, params: str = "") -> list:
    """Query Supabase REST API. Falls back to psycopg2 if DB URL is set."""
    db_url = os.environ.get("SUPABASE_DB_URL")
    if db_url:
        return _pg_query(table, params)

    key = SUPABASE_KEY
    if not key:
        return []
    result = subprocess.run(
        [
            "curl", "-sk", "--max-time", "15",
            f"{SUPABASE_URL}/rest/v1/{table}?{params}",
            "-H", f"apikey: {key}",
            "-H", f"Authorization: Bearer {key}",
            "-H", "Accept: application/json",
        ],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(result.stdout)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _pg_query(table: str, params: str) -> list:
    """Direct PostgreSQL fallback (used when SUPABASE_DB_URL is set)."""
    import psycopg2

    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        return []
    # This is a simplified fallback; main path uses REST API
    return []


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
    """Query Chellegum metrics for the given date range via Supabase REST API.

    Tables:
      - fact_spend_daily: client_slug, report_date, channel, spend
        channels: 'meta', 'tiktok' (web ads), 'tiktok_gmvmax' (GMV Max)
      - fact_kpi_daily: client_slug, report_date, revenue, orders
        (Shopify purchase value — used as Meta/TikTok web purchase value)
      - fact_tiktok_gmvmax_daily: client_slug, report_date, spend, revenue, roas
        (GMV Max has its own purchase value from TikTok Shop)
    """
    logger = get_run_logger()
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()
    date_filter = f"report_date=gte.{start_str}&report_date=lte.{end_str}"

    results = {}

    # --- Meta spend ---
    meta_rows = _supabase_query(
        "fact_spend_daily",
        f"select=spend&client_slug=eq.chubble&channel=eq.meta&{date_filter}"
    )
    meta_spend = sum(float(r.get("spend", 0)) for r in meta_rows)

    # --- TikTok Ads (web) spend ---
    tiktok_rows = _supabase_query(
        "fact_spend_daily",
        f"select=spend&client_slug=eq.chubble&channel=eq.tiktok&{date_filter}"
    )
    tiktok_spend = sum(float(r.get("spend", 0)) for r in tiktok_rows)

    # --- Shopify purchase value (attributed to Meta + TikTok web) ---
    kpi_rows = _supabase_query(
        "fact_kpi_daily",
        f"select=revenue,orders&client_slug=eq.chubble&{date_filter}"
    )
    shopify_revenue = sum(float(r.get("revenue", 0)) for r in kpi_rows)

    # Split Shopify revenue proportionally between Meta and TikTok web by spend
    web_spend_total = meta_spend + tiktok_spend
    if web_spend_total > 0:
        meta_pv = shopify_revenue * (meta_spend / web_spend_total)
        tiktok_pv = shopify_revenue * (tiktok_spend / web_spend_total)
    else:
        meta_pv = shopify_revenue
        tiktok_pv = 0

    results["meta"] = {
        "spend": meta_spend,
        "purchase_value": meta_pv,
        "roas": meta_pv / meta_spend if meta_spend > 0 else 0,
    }
    results["tiktok_ads"] = {
        "spend": tiktok_spend,
        "purchase_value": tiktok_pv,
        "roas": tiktok_pv / tiktok_spend if tiktok_spend > 0 else 0,
    }

    # --- GMV Max (TikTok Shop) — has its own revenue ---
    gmv_rows = _supabase_query(
        "fact_spend_daily",
        f"select=spend&client_slug=eq.chubble&channel=eq.tiktok_gmvmax&{date_filter}"
    )
    gmv_spend = sum(float(r.get("spend", 0)) for r in gmv_rows)

    # GMV Max purchase value from dedicated table (if it exists)
    # Fall back to fact_spend_daily if fact_tiktok_gmvmax_daily doesn't exist
    gmv_detail = _supabase_query(
        "fact_tiktok_gmvmax_daily",
        f"select=spend,revenue,roas&client_slug=eq.chubble&{date_filter}"
    )
    if gmv_detail:
        gmv_spend = sum(float(r.get("spend", 0)) for r in gmv_detail)
        gmv_pv = sum(float(r.get("revenue", 0)) for r in gmv_detail)
        gmv_roas = gmv_pv / gmv_spend if gmv_spend > 0 else 0
    else:
        gmv_pv = 0
        gmv_roas = 0

    results["gmv_max"] = {
        "spend": gmv_spend,
        "purchase_value": gmv_pv,
        "roas": gmv_roas,
    }

    logger.info(f"Data fetched — Meta: ${meta_spend:.2f}, TikTok: ${tiktok_spend:.2f}, GMV: ${gmv_spend:.2f}")
    return results


@task
def format_report(data: dict, period_label: str) -> str:
    """Format the report data into a Slack message."""
    if not data:
        return ":warning: *Chellegum Report*\nNo data available for this period."

    meta = data.get("meta", {})
    tiktok = data.get("tiktok_ads", {})
    gmv = data.get("gmv_max", {})

    total_spend = meta.get("spend", 0) + tiktok.get("spend", 0) + gmv.get("spend", 0)
    total_pv = meta.get("purchase_value", 0) + tiktok.get("purchase_value", 0) + gmv.get("purchase_value", 0)
    total_roas = total_pv / total_spend if total_spend > 0 else 0

    lines = [
        ":bar_chart: *Chellegum Performance Report*",
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
