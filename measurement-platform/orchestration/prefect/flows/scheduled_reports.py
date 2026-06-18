"""
scheduled_reports.py — Automated Chubble Gum performance reports posted to Slack.

Schedules:
  - 1st of every month: previous full month of data
  - 14th of every month: last 14 days of data

Report format:
  Per-platform breakdown (spend, purchase value, ROAS):
    - Meta
    - TikTok Ads (web)
    - GMV Max (TikTok Shop)
  Combined totals: total spend, total purchase value, total ROAS

Data sources (public_marts schema, populated by dbt):
  - fact_spend_daily: client_slug, report_date, channel, spend
    channels: 'meta', 'tiktok' (web ads), 'tiktok_gmvmax' (GMV Max)
  - fact_kpi_daily: client_slug, report_date, revenue, orders
    (Shopify purchase value — attributed proportionally to Meta/TikTok web)
  - fact_tiktok_gmvmax_daily: client_slug, report_date, spend, revenue, roas
    (GMV Max has its own purchase value from TikTok Shop)
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

# Schema where dbt materializes tables
MARTS_SCHEMA = "public_marts"


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
    """Get a psycopg2 connection using SUPABASE_DB_URL."""
    import psycopg2

    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        return None
    return psycopg2.connect(db_url, connect_timeout=15)


def _pg_query_sql(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SQL query via psycopg2 and return rows as dicts."""
    conn = _get_pg_connection()
    if not conn:
        return []
    try:
        import psycopg2.extras

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"PostgreSQL query failed: {e}")
        return []
    finally:
        conn.close()


def _rest_query(table: str, params: str = "") -> list | None:
    """Query Supabase REST API (public schema only).

    Returns:
      - list: successful query (possibly empty)
      - None: transport/auth/API failure
    """
    key = SUPABASE_KEY
    if not key:
        print("Supabase REST query failed: SUPABASE_SERVICE_KEY is not set")
        return None
    result = subprocess.run(
        [
            "curl", "-sk", "--max-time", "15",
            f"{SUPABASE_URL}/rest/v1/{table}?{params}",
            "-H", f"apikey: {key}",
            "-H", f"Authorization: Bearer {key}",
            "-H", "Accept: application/json",
            "-w", r"\n%{http_code}",
        ],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        print(f"Supabase REST query failed: curl exit={result.returncode}, stderr={result.stderr.strip()}")
        return None

    try:
        body, http_code_str = result.stdout.rsplit("\n", 1)
        http_code = int(http_code_str.strip())
    except Exception:
        print("Supabase REST query failed: could not parse HTTP status code")
        return None

    if http_code != 200:
        print(f"Supabase REST query failed: http_status={http_code}, body={body}")
        return None

    try:
        data = json.loads(body)
        return data if isinstance(data, list) else None
    except Exception:
        print("Supabase REST query failed: invalid JSON response")
        return None


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


def _fetch_via_postgres(start_date: date, end_date: date) -> dict | None:
    """Fetch report data directly from PostgreSQL (public_marts schema)."""
    conn = _get_pg_connection()
    if not conn:
        return None

    try:
        import psycopg2.extras

        results = {}

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # --- Meta spend ---
            cur.execute(f"""
                SELECT COALESCE(SUM(spend), 0) AS total_spend
                FROM {MARTS_SCHEMA}.fact_spend_daily
                WHERE client_slug = 'chubble'
                  AND channel = 'meta'
                  AND report_date BETWEEN %s AND %s
            """, (start_date, end_date))
            meta_spend = float(cur.fetchone()["total_spend"])

            # --- TikTok Ads (web) spend ---
            cur.execute(f"""
                SELECT COALESCE(SUM(spend), 0) AS total_spend
                FROM {MARTS_SCHEMA}.fact_spend_daily
                WHERE client_slug = 'chubble'
                  AND channel = 'tiktok'
                  AND report_date BETWEEN %s AND %s
            """, (start_date, end_date))
            tiktok_spend = float(cur.fetchone()["total_spend"])

            # --- Shopify purchase value (attributed to Meta + TikTok web) ---
            cur.execute(f"""
                SELECT COALESCE(SUM(revenue), 0) AS total_revenue
                FROM {MARTS_SCHEMA}.fact_kpi_daily
                WHERE client_slug = 'chubble'
                  AND report_date BETWEEN %s AND %s
            """, (start_date, end_date))
            shopify_revenue = float(cur.fetchone()["total_revenue"])

            # Split Shopify revenue proportionally between Meta and TikTok web
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
            cur.execute(f"""
                SELECT
                    COALESCE(SUM(cost), 0) AS total_spend,
                    COALESCE(SUM(gross_revenue), 0) AS total_revenue
                FROM {MARTS_SCHEMA}.fact_tiktok_gmv_max_daily
                WHERE client_slug = 'chubble'
                  AND report_date BETWEEN %s AND %s
            """, (start_date, end_date))
            gmv_row = cur.fetchone()
            gmv_spend = float(gmv_row["total_spend"])
            gmv_pv = float(gmv_row["total_revenue"])
            gmv_roas = gmv_pv / gmv_spend if gmv_spend > 0 else 0

            results["gmv_max"] = {
                "spend": gmv_spend,
                "purchase_value": gmv_pv,
                "roas": gmv_roas,
            }

        return results
    except Exception as e:
        print(f"PostgreSQL fetch failed: {e}")
        return None
    finally:
        conn.close()


def _fetch_via_rest(start_date: date, end_date: date) -> dict | None:
    """Fetch report data via Supabase REST API (public schema fallback)."""
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()
    date_filter = f"report_date=gte.{start_str}&report_date=lte.{end_str}"

    results = {}

    # --- Meta spend ---
    meta_rows = _rest_query(
        "fact_spend_daily",
        f"select=spend&client_slug=eq.chubble&channel=eq.meta&{date_filter}"
    )
    if meta_rows is None:
        return None
    meta_spend = sum(float(r.get("spend", 0)) for r in meta_rows)

    # --- TikTok Ads (web) spend ---
    tiktok_rows = _rest_query(
        "fact_spend_daily",
        f"select=spend&client_slug=eq.chubble&channel=eq.tiktok&{date_filter}"
    )
    if tiktok_rows is None:
        return None
    tiktok_spend = sum(float(r.get("spend", 0)) for r in tiktok_rows)

    # --- Shopify purchase value ---
    kpi_rows = _rest_query(
        "fact_kpi_daily",
        f"select=revenue,orders&client_slug=eq.chubble&{date_filter}"
    )
    if kpi_rows is None:
        return None
    shopify_revenue = sum(float(r.get("revenue", 0)) for r in kpi_rows)

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

    # --- GMV Max ---
    gmv_detail = _rest_query(
        "fact_tiktok_gmvmax_daily",
        f"select=spend,revenue,roas&client_slug=eq.chubble&{date_filter}"
    )
    if gmv_detail:
        gmv_spend = sum(float(r.get("spend", 0)) for r in gmv_detail)
        gmv_pv = sum(float(r.get("revenue", 0)) for r in gmv_detail)
    else:
        # Dedicated GMV table may not exist in some environments; fall back to spend-only channel data.
        gmv_rows = _rest_query(
            "fact_spend_daily",
            f"select=spend&client_slug=eq.chubble&channel=eq.tiktok_gmvmax&{date_filter}"
        )
        if gmv_rows is None:
            return None
        gmv_spend = sum(float(r.get("spend", 0)) for r in gmv_rows)
        gmv_pv = 0

    gmv_roas = gmv_pv / gmv_spend if gmv_spend > 0 else 0
    results["gmv_max"] = {
        "spend": gmv_spend,
        "purchase_value": gmv_pv,
        "roas": gmv_roas,
    }

    return results


@task
def fetch_report_data(start_date: date, end_date: date) -> dict:
    """Query Chubble Gum metrics for the given date range.

    Primary: direct PostgreSQL to public_marts schema (via SUPABASE_DB_URL).
    Fallback: Supabase REST API (public schema — requires views or schema exposure).
    """
    logger = get_run_logger()

    # Try direct PostgreSQL first (accesses public_marts schema)
    data = _fetch_via_postgres(start_date, end_date)
    if data:
        meta_spend = data.get("meta", {}).get("spend", 0)
        tiktok_spend = data.get("tiktok_ads", {}).get("spend", 0)
        gmv_spend = data.get("gmv_max", {}).get("spend", 0)
        logger.info(f"Data fetched via PostgreSQL — Meta: ${meta_spend:.2f}, TikTok: ${tiktok_spend:.2f}, GMV: ${gmv_spend:.2f}")
        return data

    # Fallback to REST API
    logger.info("PostgreSQL unavailable, falling back to REST API")
    data = _fetch_via_rest(start_date, end_date)
    if data:
        meta_spend = data.get("meta", {}).get("spend", 0)
        tiktok_spend = data.get("tiktok_ads", {}).get("spend", 0)
        gmv_spend = data.get("gmv_max", {}).get("spend", 0)
        logger.info(f"Data fetched via REST — Meta: ${meta_spend:.2f}, TikTok: ${tiktok_spend:.2f}, GMV: ${gmv_spend:.2f}")
    return data


@task
def format_report(data: dict, period_label: str) -> str:
    """Format the report data into a Slack message."""
    if not data:
        return ":warning: *Chubble Gum Report*\nNo data available for this period."

    meta = data.get("meta", {})
    tiktok = data.get("tiktok_ads", {})
    gmv = data.get("gmv_max", {})

    total_spend = meta.get("spend", 0) + tiktok.get("spend", 0) + gmv.get("spend", 0)
    total_pv = meta.get("purchase_value", 0) + tiktok.get("purchase_value", 0) + gmv.get("purchase_value", 0)
    total_roas = total_pv / total_spend if total_spend > 0 else 0

    lines = [
        ":bar_chart: *Chubble Gum Performance Report*",
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


@flow(name="chellegum_scheduled_report", description="Chubble Gum bi-monthly performance report (1st and 14th)")
def chellegum_scheduled_report() -> None:
    """Generate and post the Chubble Gum performance report to Slack.

    Runs on the 1st (previous month) and 14th (last 14 days) of each month.
    Posts to the #chubblegum Slack channel (C0AEXRYPA9Y).
    """
    logger = get_run_logger()
    today = date.today()

    start_date, end_date, period_label = _compute_period(today)
    logger.info(f"Generating Chubble Gum report: {period_label} ({start_date} to {end_date})")

    data = fetch_report_data.submit(start_date, end_date).result()

    if not data:
        logger.warning("No data returned; posting warning to Slack")
        _post_slack_message(
            ":warning: *Chubble Gum Report*\n"
            f"Period: {period_label}\n"
            "Could not fetch report data. Check database connection."
        )
        return

    report = format_report.submit(data, period_label).result()
    logger.info("Report formatted, posting to Slack")

    _post_slack_message(report)
    logger.info("Chubble Gum report posted to #chubblegum")


if __name__ == "__main__":
    chellegum_scheduled_report()
