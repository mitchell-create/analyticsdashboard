"""
tiktok_sync.py — Sync TikTok Ads daily advertiser reports to Postgres.

Direct TikTok Marketing API replacement for the dead Airbyte
`tiktok_advertisers_reports_daily` source. Pulls BASIC advertiser-level daily
metrics (spend, impressions, clicks, conversions, ...) for the tiktok advertisers
in client_ad_accounts.csv into `raw.tiktok_advertisers_reports_daily`
(advertiser_id, stat_time_day, metrics JSON) — the exact shape stg_tiktok_spend
already expects.

Auth: a long-lived access token from tiktok_auth.py (tiktok_credentials.json) or
the TIKTOK_ACCESS_TOKEN env var. See tiktok_auth.py to mint one.

    cd measurement-platform
    python orchestration\\tiktok_sync.py                       # 45-day lookback, all tiktok accounts
    python orchestration\\tiktok_sync.py --client nexocore --dry-run
"""

import argparse
import csv
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError:  # only needed for the DB write, not --dry-run
    psycopg2 = None

API_URL = "https://business-api.tiktok.com/open_api/v1.3/report/integrated/get/"
RAW_TABLE = "raw.tiktok_advertisers_reports_daily"
DEFAULT_LOOKBACK_DAYS = 45
MAX_WINDOW_DAYS = 30        # TikTok caps the integrated-report date range per request
PAGE_SIZE = 1000
REQUEST_INTERVAL = 0.3
METRICS = ["spend", "impressions", "clicks", "conversion",
           "cost_per_conversion", "ctr", "cpc", "cpm"]


def load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())


def get_access_token():
    creds = Path(__file__).resolve().parent.parent / "tiktok_credentials.json"
    if creds.exists():
        try:
            tok = json.loads(creds.read_text()).get("access_token")
            if tok:
                return tok
        except Exception:
            pass
    tok = os.environ.get("TIKTOK_ACCESS_TOKEN")
    if tok:
        return tok
    print("ERROR: no TikTok access token — run tiktok_auth.py or set TIKTOK_ACCESS_TOKEN")
    sys.exit(1)


def load_tiktok_accounts(client_filter=None):
    seed = (Path(__file__).resolve().parent.parent / "dbt" / "seeds" / "client_ad_accounts.csv")
    accounts = []
    with open(seed, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("platform", "").strip().lower() != "tiktok":
                continue
            slug = row["client_slug"].strip().lower()
            if client_filter and slug != client_filter.lower():
                continue
            accounts.append({"slug": slug, "advertiser_id": row["account_id"].strip()})
    return accounts


def _date_windows(start_date, end_date, max_days=MAX_WINDOW_DAYS):
    s = datetime.strptime(start_date, "%Y-%m-%d").date()
    e = datetime.strptime(end_date, "%Y-%m-%d").date()
    while s <= e:
        w_end = min(s + timedelta(days=max_days - 1), e)
        yield s.isoformat(), w_end.isoformat()
        s = w_end + timedelta(days=1)


def fetch_advertiser_report(advertiser_id, access_token, start_date, end_date):
    """Paginated BASIC advertiser-level daily report, chunked to TikTok's window limit."""
    headers = {"Access-Token": access_token}
    rows = []
    for w_start, w_end in _date_windows(start_date, end_date):
        page = 1
        while True:
            params = {
                "advertiser_id": advertiser_id,
                "report_type": "BASIC",
                "data_level": "AUCTION_ADVERTISER",
                "dimensions": json.dumps(["advertiser_id", "stat_time_day"]),
                "metrics": json.dumps(METRICS),
                "start_date": w_start,
                "end_date": w_end,
                "page": page,
                "page_size": PAGE_SIZE,
            }
            time.sleep(REQUEST_INTERVAL)
            resp = requests.get(API_URL, headers=headers, params=params, timeout=60)
            body = resp.json()
            if body.get("code") != 0:
                raise RuntimeError(
                    f"TikTok API error ({body.get('code')}): {body.get('message')}")
            data = body.get("data", {})
            for item in data.get("list", []):
                dims = item.get("dimensions", {})
                rows.append({
                    "advertiser_id": str(dims.get("advertiser_id", advertiser_id)),
                    "stat_time_day": dims.get("stat_time_day"),
                    "metrics": item.get("metrics", {}),
                })
            page_info = data.get("page_info", {})
            if page >= int(page_info.get("total_page", 1) or 1):
                break
            page += 1
    return rows


# ─── Database ───────────────────────────────────────────────────────────────
def get_db_connection():
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: SUPABASE_DB_URL not set")
        sys.exit(1)
    if psycopg2 is None:
        print("ERROR: psycopg2 not installed (needed for DB write)")
        sys.exit(1)
    return psycopg2.connect(db_url, connect_timeout=20)


def ensure_table(conn):
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {RAW_TABLE} (
            advertiser_id text,
            stat_time_day text,
            metrics jsonb,
            _airbyte_raw_id text,
            _airbyte_extracted_at timestamptz,
            _airbyte_meta jsonb,
            _airbyte_generation_id bigint
        );
    """)
    conn.commit()


def replace_advertiser_range(conn, advertiser_id, start_date, end_date, rows, dry_run=False):
    if dry_run:
        return len(rows)
    cur = conn.cursor()
    try:
        cur.execute(
            f"DELETE FROM {RAW_TABLE} WHERE advertiser_id::text = %s "
            f"AND (stat_time_day::date) BETWEEN %s AND %s",
            (advertiser_id, start_date, end_date),
        )
        for r in rows:
            cur.execute(
                f"INSERT INTO {RAW_TABLE} (advertiser_id, stat_time_day, metrics, "
                f"_airbyte_raw_id, _airbyte_extracted_at, _airbyte_meta) "
                f"VALUES (%s, %s, %s, %s, %s, %s)",
                (r["advertiser_id"], r["stat_time_day"], Json(r["metrics"]),
                 str(uuid.uuid4()), datetime.now(timezone.utc),
                 Json({"source": "tiktok_sync.py"})),
            )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise


def run(start_date=None, end_date=None, client_filter=None, dry_run=False):
    load_env()
    access_token = get_access_token()
    accounts = load_tiktok_accounts(client_filter)
    if not accounts:
        print(f"No TikTok accounts found"
              f"{' for ' + client_filter if client_filter else ''} in client_ad_accounts.csv")
        sys.exit(1)

    today = datetime.now(timezone.utc).date()
    end_date = end_date or today.isoformat()
    start_date = start_date or (today - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()

    print(f"TikTok Sync - {len(accounts)} account(s), {start_date} to {end_date}")
    if dry_run:
        print("DRY RUN - no data will be written")

    conn = None if dry_run else get_db_connection()
    if conn:
        ensure_table(conn)

    grand_rows = 0
    grand_spend = 0.0
    for acct in accounts:
        adv = acct["advertiser_id"]
        print(f"\n  {acct['slug']} ({adv})", end="")
        try:
            rows = fetch_advertiser_report(adv, access_token, start_date, end_date)
        except Exception as e:
            print(f"\n    ERROR: {e}")
            continue
        spend = sum(float(r["metrics"].get("spend", 0) or 0) for r in rows)
        print(f"  {len(rows)} day-rows | spend {spend:,.2f}", end="")
        written = replace_advertiser_range(conn, adv, start_date, end_date, rows, dry_run)
        print(f" -> {'(dry-run) ' if dry_run else ''}{written} rows")
        grand_rows += len(rows)
        grand_spend += spend
    if conn:
        conn.close()

    print(f"\n{'=' * 60}")
    print(f"DONE - {grand_rows} day-rows across {len(accounts)} account(s), total spend {grand_spend:,.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync TikTok Ads data to Postgres")
    parser.add_argument("--client", help="Sync only this client slug")
    parser.add_argument("--start-date", default=None,
                        help=f"Start date YYYY-MM-DD (default: {DEFAULT_LOOKBACK_DAYS} days ago)")
    parser.add_argument("--end-date", default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch + preview, no DB write")
    args = parser.parse_args()

    run(start_date=args.start_date, end_date=args.end_date,
        client_filter=args.client, dry_run=args.dry_run)
