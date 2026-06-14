"""
google_ads_sync.py — Direct Google Ads API sync to Postgres, replacing Airbyte.

Pulls account-level daily metrics (cost, impressions, clicks) for each client's
Google Ads account and writes them to raw.google_account_performance_report,
which feeds stg_google_spend -> fact_spend_daily.

REST-based (no google-ads library): refreshes an OAuth access token, then runs
a GAQL query via googleAds:searchStream per account. Idempotent
delete-then-insert per account/date window.

Usage:
    python google_ads_sync.py                          # default window, all accounts
    python google_ads_sync.py --client chubble         # one client
    python google_ads_sync.py --start-date 2026-04-05  # explicit backfill start
    python google_ads_sync.py --dry-run                # preview without writing

Env (measurement-platform/.env):
    SUPABASE_DB_URL                — Postgres connection string
    GOOGLE_ADS_DEVELOPER_TOKEN     — from the MCC API Center
    GOOGLE_ADS_CLIENT_ID           — OAuth client id
    GOOGLE_ADS_CLIENT_SECRET       — OAuth client secret
    GOOGLE_ADS_REFRESH_TOKEN       — from google_ads_auth.py (adwords scope)
    GOOGLE_ADS_LOGIN_CUSTOMER_ID   — manager (MCC) id, digits only (e.g. 9346840592)
"""

import argparse
import csv
import json
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import requests

# ─── Configuration ────────────────────────────────────────────────────────────

API_VERSION = "v18"  # bump if the API returns a version/deprecation error
TOKEN_URL = "https://oauth2.googleapis.com/token"
RAW_TABLE = "raw.google_account_performance_report"
DEFAULT_LOOKBACK_DAYS = 45
REQUEST_INTERVAL = 0.3
MAX_RETRIES = 4

GAQL = (
    "SELECT customer.id, segments.date, metrics.cost_micros, "
    "metrics.impressions, metrics.clicks "
    "FROM customer "
    "WHERE segments.date BETWEEN '{start}' AND '{end}'"
)


def load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())


def load_google_accounts(client_filter=None):
    """Read Google accounts (customer ids) from the client_ad_accounts seed."""
    seed = (Path(__file__).resolve().parent.parent
            / "dbt" / "seeds" / "client_ad_accounts.csv")
    accounts = []
    with open(seed, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("platform", "").strip().lower() != "google":
                continue
            slug = row["client_slug"].strip().lower()
            if client_filter and slug != client_filter.lower():
                continue
            # customer ids must be digits only (no dashes) for the API
            accounts.append({"slug": slug, "customer_id": row["account_id"].strip().replace("-", "")})
    return accounts


# ─── Google Ads API ───────────────────────────────────────────────────────────

def get_access_token(client_id, client_secret, refresh_token):
    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"OAuth token refresh failed {resp.status_code}: {resp.text[:300]}")
    return resp.json()["access_token"]


def fetch_account_metrics(customer_id, access_token, dev_token, login_customer_id,
                          start_date, end_date):
    """Run the GAQL query for one account; return parsed daily rows."""
    url = f"https://googleads.googleapis.com/{API_VERSION}/customers/{customer_id}/googleAds:searchStream"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "developer-token": dev_token,
        "login-customer-id": login_customer_id,
        "Content-Type": "application/json",
    }
    body = {"query": GAQL.format(start=start_date, end=end_date)}

    for attempt in range(MAX_RETRIES + 1):
        time.sleep(REQUEST_INTERVAL)
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=120)
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            raise
        if resp.status_code == 200:
            break
        if resp.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"Google Ads API {resp.status_code}: {resp.text[:400]}")
    else:
        raise RuntimeError(f"Failed after {MAX_RETRIES} retries: customer {customer_id}")

    rows = []
    for batch in resp.json():  # searchStream returns a list of result batches
        for r in batch.get("results", []):
            rows.append({
                "customer_id": r["customer"]["id"],
                "segments_date": r["segments"]["date"],
                "metrics_cost_micros": int(r["metrics"].get("costMicros", 0)),
                "metrics_impressions": int(r["metrics"].get("impressions", 0)),
                "metrics_clicks": int(r["metrics"].get("clicks", 0)),
            })
    return rows


# ─── Database ─────────────────────────────────────────────────────────────────

def get_db_connection():
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: SUPABASE_DB_URL not set")
        sys.exit(1)
    return psycopg2.connect(db_url, connect_timeout=20)


def replace_account_range(conn, customer_id, start_date, end_date, rows, dry_run=False):
    if dry_run:
        return len(rows)
    cur = conn.cursor()
    try:
        cur.execute(
            f"DELETE FROM {RAW_TABLE} WHERE customer_id::text = %s "
            f"AND segments_date::date BETWEEN %s AND %s",
            (customer_id, start_date, end_date),
        )
        for r in rows:
            cur.execute(
                f"""INSERT INTO {RAW_TABLE} (
                        _airbyte_raw_id, _airbyte_extracted_at, _airbyte_meta, _airbyte_generation_id,
                        customer_id, segments_date, metrics_cost_micros,
                        metrics_impressions, metrics_clicks
                    ) VALUES (%s, now(), %s, 0, %s, %s, %s, %s, %s)""",
                (
                    str(uuid.uuid4()), json.dumps({"source": "google_ads_sync.py"}),
                    r["customer_id"], r["segments_date"], r["metrics_cost_micros"],
                    r["metrics_impressions"], r["metrics_clicks"],
                ),
            )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise


# ─── Sync ─────────────────────────────────────────────────────────────────────

def run(start_date=None, end_date=None, client_filter=None, dry_run=False):
    load_env()

    dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_ADS_REFRESH_TOKEN")
    login_customer_id = (os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID") or "").replace("-", "")
    missing = [k for k, v in {
        "GOOGLE_ADS_DEVELOPER_TOKEN": dev_token, "GOOGLE_ADS_CLIENT_ID": client_id,
        "GOOGLE_ADS_CLIENT_SECRET": client_secret, "GOOGLE_ADS_REFRESH_TOKEN": refresh_token,
        "GOOGLE_ADS_LOGIN_CUSTOMER_ID": login_customer_id,
    }.items() if not v]
    if missing:
        print(f"ERROR: missing env vars: {', '.join(missing)}")
        sys.exit(1)

    accounts = load_google_accounts(client_filter)
    if not accounts:
        print(f"No Google accounts found"
              f"{' for ' + client_filter if client_filter else ''} in client_ad_accounts.csv")
        sys.exit(1)

    today = datetime.now(timezone.utc).date()
    if not end_date:
        end_date = today.isoformat()
    if not start_date:
        start_date = (today - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()

    print(f"Google Ads Sync - {len(accounts)} account(s), {start_date} to {end_date}")
    if dry_run:
        print("DRY RUN - no data will be written")

    print("Refreshing access token...", end=" ", flush=True)
    access_token = get_access_token(client_id, client_secret, refresh_token)
    print("ok")

    conn = None if dry_run else get_db_connection()
    grand_rows = 0
    grand_spend = 0.0
    for acct in accounts:
        print(f"\n  {acct['slug']} ({acct['customer_id']})", end="")
        try:
            rows = fetch_account_metrics(
                acct["customer_id"], access_token, dev_token, login_customer_id,
                start_date, end_date,
            )
        except Exception as e:
            print(f"\n    ERROR: {e}")
            continue
        spend = sum(r["metrics_cost_micros"] for r in rows) / 1e6
        print(f"  {len(rows)} daily rows | spend ${spend:,.2f}", end="")
        written = replace_account_range(conn, acct["customer_id"], start_date, end_date, rows, dry_run)
        print(f" -> {'(dry-run) ' if dry_run else ''}{written} rows")
        grand_rows += len(rows)
        grand_spend += spend
    if conn:
        conn.close()

    print(f"\n{'='*60}")
    print(f"DONE - {grand_rows} daily rows across {len(accounts)} account(s)")
    print(f"  Total spend: ${grand_spend:,.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Google Ads data to Postgres")
    parser.add_argument("--client", help="Sync only this client slug")
    parser.add_argument("--start-date", default=None,
                        help=f"Start date YYYY-MM-DD (default: {DEFAULT_LOOKBACK_DAYS} days ago)")
    parser.add_argument("--end-date", default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    run(start_date=args.start_date, end_date=args.end_date,
        client_filter=args.client, dry_run=args.dry_run)
