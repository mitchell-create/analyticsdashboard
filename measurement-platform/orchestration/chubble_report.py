"""
chubble_report.py — Chubble Gum Performance Report for Slack.
Uses platform-reported purchase values (not Shopify-split).

Usage:
    python chubble_report.py              # post to #chubblegum
    python chubble_report.py --dry-run    # print without posting
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg2
import psycopg2.extras


def load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())


def get_report_dates():
    """Determine report period: 1st = previous full month, 14th = last 14 days."""
    today = date.today()
    if today.day <= 2:
        end_date = today - timedelta(days=today.day)
        start_date = end_date.replace(day=1)
        label = f'{start_date.strftime("%B %Y")} (Full Month)'
    else:
        end_date = today - timedelta(days=1)
        start_date = today - timedelta(days=14)
        label = f'{start_date.strftime("%b %d")} - {end_date.strftime("%b %d, %Y")} (Last 14 Days)'
    return start_date, end_date, label


def get_meta_metrics(cur, start_date, end_date):
    """Get Meta spend and platform-reported purchase value from action_values."""
    cur.execute("""
        SELECT d.date_start::date, d.spend::numeric, d.action_values::text
        FROM raw.meta_customaccount_insights_daily d
        JOIN public.client_ad_accounts a ON d.account_id = a.account_id
        WHERE a.client_slug = 'chubble' AND a.platform = 'meta'
          AND d.date_start::date BETWEEN %s AND %s
    """, (start_date, end_date))

    total_spend = 0
    total_pv = 0
    for row in cur.fetchall():
        total_spend += float(row["spend"])
        av = json.loads(row["action_values"]) if row["action_values"] else []
        for a in av:
            if a.get("action_type") == "omni_purchase":
                total_pv += float(a.get("value", 0))

    return {"spend": total_spend, "purchase_value": total_pv}


def get_google_metrics(cur, start_date, end_date):
    """Get Google Ads spend and conversions value."""
    cur.execute("""
        SELECT COALESCE(SUM(d.metrics_cost_micros::numeric / 1000000), 0) AS spend,
               COALESCE(SUM(d.metrics_conversions_value::numeric), 0) AS purchase_value
        FROM raw.google_account_performance_report d
        JOIN public.client_ad_accounts a ON d.customer_id::text = a.account_id
        WHERE a.client_slug = 'chubble' AND a.platform = 'google'
          AND d.segments_date::date BETWEEN %s AND %s
    """, (start_date, end_date))
    row = cur.fetchone()
    return {
        "spend": float(row["spend"]),
        "purchase_value": float(row["purchase_value"]),
    }


def get_tiktok_web_metrics(cur, start_date, end_date):
    """Get TikTok web ads spend. Purchase value not available from connector."""
    cur.execute("""
        SELECT COALESCE(SUM(spend), 0) AS spend
        FROM public_marts.fact_spend_daily
        WHERE client_slug = 'chubble' AND channel = 'tiktok'
          AND report_date BETWEEN %s AND %s
    """, (start_date, end_date))
    spend = float(cur.fetchone()["spend"])
    return {"spend": spend, "purchase_value": None}


def get_gmv_max_metrics(cur, start_date, end_date):
    """Get TikTok GMV Max spend and revenue."""
    cur.execute("""
        SELECT COALESCE(SUM(cost), 0) AS spend,
               COALESCE(SUM(gross_revenue), 0) AS purchase_value
        FROM public_marts.fact_tiktok_gmv_max_daily
        WHERE client_slug = 'chubble'
          AND report_date BETWEEN %s AND %s
    """, (start_date, end_date))
    row = cur.fetchone()
    return {
        "spend": float(row["spend"]),
        "purchase_value": float(row["purchase_value"]),
    }


def get_shopify_revenue(cur, start_date, end_date):
    """Get total Shopify revenue for reference."""
    cur.execute("""
        SELECT COALESCE(SUM(revenue), 0) AS revenue,
               COALESCE(SUM(orders), 0) AS orders
        FROM public_marts.fact_kpi_daily
        WHERE client_slug = 'chubble'
          AND report_date BETWEEN %s AND %s
    """, (start_date, end_date))
    row = cur.fetchone()
    return {"revenue": float(row["revenue"]), "orders": int(row["orders"])}


def fc(v):
    """Format currency."""
    return f'${v:,.2f}'


def fr(v):
    """Format ROAS."""
    return f'{v:.2f}x'


def build_report(start_date, end_date, label):
    """Build the report text."""
    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    meta = get_meta_metrics(cur, start_date, end_date)
    google = get_google_metrics(cur, start_date, end_date)
    tiktok = get_tiktok_web_metrics(cur, start_date, end_date)
    gmv = get_gmv_max_metrics(cur, start_date, end_date)
    shopify = get_shopify_revenue(cur, start_date, end_date)

    conn.close()

    meta_roas = meta["purchase_value"] / meta["spend"] if meta["spend"] > 0 else 0
    google_roas = google["purchase_value"] / google["spend"] if google["spend"] > 0 else 0
    gmv_roas = gmv["purchase_value"] / gmv["spend"] if gmv["spend"] > 0 else 0

    # Total: sum all platforms with known purchase values
    total_spend = meta["spend"] + google["spend"] + tiktok["spend"] + gmv["spend"]
    # Only sum purchase values where we have platform-reported data
    total_pv = meta["purchase_value"] + google["purchase_value"] + gmv["purchase_value"]
    total_roas = total_pv / total_spend if total_spend > 0 else 0

    # MER = Shopify revenue / total ad spend
    mer = shopify["revenue"] / total_spend if total_spend > 0 else 0

    report = ':bar_chart: *Chubble Gum Performance Report*\n'
    report += f'*{label}*\n\n'

    report += f'*Meta Ads*\n'
    report += f'  Spend: {fc(meta["spend"])}\n'
    report += f'  Purchase Value: {fc(meta["purchase_value"])}\n'
    report += f'  ROAS: {fr(meta_roas)}\n\n'

    if google["spend"] > 0:
        report += f'*Google Ads*\n'
        report += f'  Spend: {fc(google["spend"])}\n'
        report += f'  Conversion Value: {fc(google["purchase_value"])}\n'
        report += f'  ROAS: {fr(google_roas)}\n\n'

    report += f'*TikTok Ads (Web)*\n'
    report += f'  Spend: {fc(tiktok["spend"])}\n'
    report += f'  Purchase Value: _not tracked by connector_\n\n'

    report += f'*GMV Max (TikTok Shop)*\n'
    report += f'  Spend: {fc(gmv["spend"])}\n'
    report += f'  Purchase Value: {fc(gmv["purchase_value"])}\n'
    report += f'  ROAS: {fr(gmv_roas)}\n\n'

    report += f'*TOTALS*\n'
    report += f'  Total Ad Spend: {fc(total_spend)}\n'
    report += f'  Platform Purchase Value: {fc(total_pv)}\n'
    report += f'  Blended ROAS: {fr(total_roas)}\n\n'

    report += f'*Shopify Revenue*\n'
    report += f'  Revenue: {fc(shopify["revenue"])}\n'
    report += f'  Orders: {shopify["orders"]:,}\n'
    report += f'  MER (Revenue/Spend): {fr(mer)}\n'

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env()
    start_date, end_date, label = get_report_dates()
    report = build_report(start_date, end_date, label)

    if args.dry_run:
        print(report)
        return

    from slack_sdk import WebClient
    client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    result = client.chat_postMessage(channel="C0AEXRYPA9Y", text=report)
    print(f'Report posted to #chubblegum: {result["ok"]}')


if __name__ == "__main__":
    main()
