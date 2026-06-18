#!/usr/bin/env python3
"""
Run the Chellegum performance report manually (outside of Prefect).

Usage:
  # Set env vars first:
  export SUPABASE_DB_URL="postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres"
  export SLACK_BOT_TOKEN="xoxb-..."

  # Run the report:
  python3 scripts/run_chellegum_report.py

  # Or with --setup-views to create public schema views first:
  python3 scripts/run_chellegum_report.py --setup-views

Prerequisites:
  pip install psycopg2-binary slack_sdk
"""

import os
import sys
from datetime import date, timedelta

CHUBBLEGUM_CHANNEL_ID = "C0AEXRYPA9Y"
MARTS_SCHEMA = "public_marts"


def get_connection():
    import psycopg2
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: Set SUPABASE_DB_URL environment variable")
        sys.exit(1)
    return psycopg2.connect(db_url, connect_timeout=15)


def setup_views():
    """Create public schema views pointing to public_marts tables."""
    conn = get_connection()
    cur = conn.cursor()

    print("Creating views in public schema -> public_marts...")

    cur.execute("DROP TABLE IF EXISTS public.fact_spend_daily CASCADE;")
    cur.execute("DROP TABLE IF EXISTS public.fact_kpi_daily CASCADE;")

    cur.execute("""
        CREATE OR REPLACE VIEW public.fact_spend_daily AS
        SELECT client_slug, report_date, channel, spend, impressions, clicks
        FROM public_marts.fact_spend_daily;
    """)
    cur.execute("""
        CREATE OR REPLACE VIEW public.fact_kpi_daily AS
        SELECT client_slug, report_date, revenue, orders
        FROM public_marts.fact_kpi_daily;
    """)
    cur.execute("""
        CREATE OR REPLACE VIEW public.fact_tiktok_gmvmax_daily AS
        SELECT client_slug, report_date, cost AS spend, orders, gross_revenue AS revenue, cost_per_order, roas
        FROM public_marts.fact_tiktok_gmv_max_daily;
    """)

    # Restrict REST-accessible views to service_role to avoid cross-client data exposure.
    cur.execute("REVOKE ALL ON public.fact_spend_daily FROM anon, authenticated;")
    cur.execute("REVOKE ALL ON public.fact_kpi_daily FROM anon, authenticated;")
    cur.execute("REVOKE ALL ON public.fact_tiktok_gmvmax_daily FROM anon, authenticated;")
    cur.execute("GRANT SELECT ON public.fact_spend_daily TO service_role;")
    cur.execute("GRANT SELECT ON public.fact_kpi_daily TO service_role;")
    cur.execute("GRANT SELECT ON public.fact_tiktok_gmvmax_daily TO service_role;")

    conn.commit()
    cur.close()
    conn.close()
    print("Views created successfully!")


def fmt_currency(val):
    if val is None:
        return "$0.00"
    num = float(val)
    if num >= 1_000_000:
        return f"${num:,.0f}"
    return f"${num:,.2f}"


def fmt_roas(val):
    if val is None or float(val) == 0:
        return "0.00x"
    return f"{float(val):.2f}x"


def fetch_and_post():
    import psycopg2.extras

    conn = get_connection()

    today = date.today()
    if today.day == 1:
        end_date = today - timedelta(days=1)
        start_date = end_date.replace(day=1)
        label = f"{start_date.strftime('%B %Y')} (Full Month)"
    else:
        end_date = today - timedelta(days=1)
        start_date = today - timedelta(days=14)
        label = f"{start_date.strftime('%b %d')} – {end_date.strftime('%b %d, %Y')} (Last 14 Days)"

    print(f"Report period: {label} ({start_date} to {end_date})")

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Meta spend
        cur.execute(f"""
            SELECT COALESCE(SUM(spend), 0) AS total
            FROM {MARTS_SCHEMA}.fact_spend_daily
            WHERE client_slug = 'chubble' AND channel = 'meta'
              AND report_date BETWEEN %s AND %s
        """, (start_date, end_date))
        meta_spend = float(cur.fetchone()["total"])

        # TikTok web spend
        cur.execute(f"""
            SELECT COALESCE(SUM(spend), 0) AS total
            FROM {MARTS_SCHEMA}.fact_spend_daily
            WHERE client_slug = 'chubble' AND channel = 'tiktok'
              AND report_date BETWEEN %s AND %s
        """, (start_date, end_date))
        tiktok_spend = float(cur.fetchone()["total"])

        # Shopify revenue
        cur.execute(f"""
            SELECT COALESCE(SUM(revenue), 0) AS total
            FROM {MARTS_SCHEMA}.fact_kpi_daily
            WHERE client_slug = 'chubble'
              AND report_date BETWEEN %s AND %s
        """, (start_date, end_date))
        shopify_revenue = float(cur.fetchone()["total"])

        # GMV Max
        cur.execute(f"""
            SELECT COALESCE(SUM(cost), 0) AS total_spend,
                   COALESCE(SUM(gross_revenue), 0) AS total_revenue
            FROM {MARTS_SCHEMA}.fact_tiktok_gmv_max_daily
            WHERE client_slug = 'chubble'
              AND report_date BETWEEN %s AND %s
        """, (start_date, end_date))
        gmv = cur.fetchone()
        gmv_spend = float(gmv["total_spend"])
        gmv_pv = float(gmv["total_revenue"])

    conn.close()

    # Attribution: split Shopify revenue by spend ratio
    web_total = meta_spend + tiktok_spend
    if web_total > 0:
        meta_pv = shopify_revenue * (meta_spend / web_total)
        tiktok_pv = shopify_revenue * (tiktok_spend / web_total)
    else:
        meta_pv = shopify_revenue
        tiktok_pv = 0

    gmv_roas = gmv_pv / gmv_spend if gmv_spend > 0 else 0
    total_spend = meta_spend + tiktok_spend + gmv_spend
    total_pv = meta_pv + tiktok_pv + gmv_pv
    total_roas = total_pv / total_spend if total_spend > 0 else 0

    print(f"\nMeta: spend={fmt_currency(meta_spend)}, PV={fmt_currency(meta_pv)}")
    print(f"TikTok: spend={fmt_currency(tiktok_spend)}, PV={fmt_currency(tiktok_pv)}")
    print(f"GMV Max: spend={fmt_currency(gmv_spend)}, PV={fmt_currency(gmv_pv)}")
    print(f"Total: spend={fmt_currency(total_spend)}, PV={fmt_currency(total_pv)}, ROAS={fmt_roas(total_roas)}")

    lines = [
        ":bar_chart: *Chellegum Performance Report*",
        f"*{label}*",
        "",
        "*Meta*",
        f"  Spend:           {fmt_currency(meta_spend)}",
        f"  Purchase Value:  {fmt_currency(meta_pv)}",
        f"  ROAS:            {fmt_roas(meta_pv / meta_spend if meta_spend > 0 else 0)}",
        "",
        "*TikTok Ads (Web)*",
        f"  Spend:           {fmt_currency(tiktok_spend)}",
        f"  Purchase Value:  {fmt_currency(tiktok_pv)}",
        f"  ROAS:            {fmt_roas(tiktok_pv / tiktok_spend if tiktok_spend > 0 else 0)}",
        "",
        "*GMV Max (TikTok Shop)*",
        f"  Spend:           {fmt_currency(gmv_spend)}",
        f"  Purchase Value:  {fmt_currency(gmv_pv)}",
        f"  ROAS:            {fmt_roas(gmv_roas)}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "*TOTALS (All Platforms)*",
        f"  Total Spend:           {fmt_currency(total_spend)}",
        f"  Total Purchase Value:  {fmt_currency(total_pv)}",
        f"  Total ROAS:            {fmt_roas(total_roas)}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    report = "\n".join(lines)
    print(f"\n--- Report ---\n{report}\n")

    # Post to Slack
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("SLACK_BOT_TOKEN not set — skipping Slack post")
        return

    from slack_sdk import WebClient
    client = WebClient(token=token)
    try:
        client.conversations_join(channel=CHUBBLEGUM_CHANNEL_ID)
    except Exception:
        pass
    resp = client.chat_postMessage(channel=CHUBBLEGUM_CHANNEL_ID, text=report)
    print(f"Posted to #chubblegum! (ts={resp['ts']})")


if __name__ == "__main__":
    if "--setup-views" in sys.argv:
        setup_views()
    fetch_and_post()
