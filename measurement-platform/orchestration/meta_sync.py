"""
meta_sync.py — Direct Meta Marketing API sync to Postgres, replacing Airbyte.

Pulls account-level daily insights (spend, impressions, link clicks, actions,
action_values) for every Meta ad account in the client_ad_accounts seed and
writes them to raw.meta_customaccount_insights_daily. That table feeds:
  - stg_meta_spend -> fact_spend_daily  (spend / impressions / clicks)
  - chubble_report.py                    (action_values -> omni_purchase ROAS)

Auth uses a Meta System User access token (never expires, tied to the business,
not a personal profile — survives profile bans). One token covers all accounts.

Usage:
    python meta_sync.py                              # sync default window, all clients
    python meta_sync.py --client chubble             # one client
    python meta_sync.py --start-date 2026-04-06      # explicit backfill start
    python meta_sync.py --dry-run                    # preview without writing

Env (in measurement-platform/.env):
    SUPABASE_DB_URL    — Postgres connection string
    META_ACCESS_TOKEN  — System User access token (EAA...)
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

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
RAW_TABLE = "raw.meta_customaccount_insights_daily"

# Default: re-pull the trailing 35 days so a bi-monthly run always overlaps the
# previous one (Meta keeps revising attributed conversions for ~28 days).
DEFAULT_LOOKBACK_DAYS = 35

RATE_LIMIT_RPM = 25
REQUEST_INTERVAL = 60.0 / RATE_LIMIT_RPM
MAX_RETRIES = 4

# Fields requested from the insights endpoint (account level, daily).
INSIGHT_FIELDS = [
    "account_id", "account_name",
    "spend", "impressions", "clicks", "inline_link_clicks",
    "reach", "frequency", "cpc", "cpm", "ctr",
    "inline_link_click_ctr", "unique_link_clicks_ctr",
    "unique_inline_link_clicks", "unique_inline_link_click_ctr",
    "cost_per_unique_click",
    "actions", "action_values", "purchase_roas", "website_purchase_roas",
]

# Columns we write (must exist in RAW_TABLE — verified against live schema).
NUMERIC_FIELDS = ["spend", "frequency", "cpc", "cpm", "ctr",
                  "inline_link_click_ctr", "unique_link_clicks_ctr",
                  "unique_inline_link_click_ctr", "cost_per_unique_click"]
BIGINT_FIELDS = ["impressions", "clicks", "inline_link_clicks",
                 "reach", "unique_inline_link_clicks"]
JSON_FIELDS = ["actions", "action_values", "purchase_roas", "website_purchase_roas"]


def load_env():
    """Load .env from the measurement-platform directory."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())


def load_meta_accounts(client_filter=None):
    """Read Meta accounts from the client_ad_accounts seed (source of truth)."""
    seed = (Path(__file__).resolve().parent.parent
            / "dbt" / "seeds" / "client_ad_accounts.csv")
    if not seed.exists():
        print(f"ERROR: seed not found at {seed}")
        sys.exit(1)
    accounts = []
    with open(seed, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("platform", "").strip().lower() != "meta":
                continue
            slug = row["client_slug"].strip().lower()
            if client_filter and slug != client_filter.lower():
                continue
            accounts.append({"slug": slug, "account_id": row["account_id"].strip()})
    return accounts


# ─── Graph API ────────────────────────────────────────────────────────────────

_last_request_time = 0.0


def _rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_INTERVAL:
        time.sleep(REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def _api_get(url, params):
    """GET the Graph API with rate limiting + retry. Returns parsed JSON."""
    for attempt in range(MAX_RETRIES + 1):
        _rate_limit()
        try:
            resp = requests.get(url, params=params, timeout=120)
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt
                print(f"    request error, retrying in {wait}s: {e}")
                time.sleep(wait)
                continue
            raise

        if resp.status_code == 200:
            return resp.json()

        # Meta rate limit / transient errors -> back off and retry
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        code = err.get("code")
        if resp.status_code == 429 or code in (4, 17, 32, 613) or resp.status_code >= 500:
            wait = min(2 ** attempt * 5, 120)
            print(f"    throttled/transient ({resp.status_code}, code={code}), waiting {wait}s...")
            time.sleep(wait)
            continue

        # Permanent error — surface it
        raise RuntimeError(f"Graph API {resp.status_code}: {err.get('message', resp.text[:300])}")

    raise RuntimeError(f"Failed after {MAX_RETRIES} retries: {url}")


def fetch_account_insights(account_id, token, start_date, end_date):
    """Fetch account-level daily insights for one account over a date range."""
    url = f"{GRAPH_BASE_URL}/act_{account_id}/insights"
    params = {
        "level": "account",
        "time_increment": 1,
        "fields": ",".join(INSIGHT_FIELDS),
        "time_range": json.dumps({"since": start_date, "until": end_date}),
        "limit": 500,
        "access_token": token,
    }
    rows = []
    data = _api_get(url, params)
    rows.extend(data.get("data", []))
    # Follow pagination
    while data.get("paging", {}).get("next"):
        data = _api_get(data["paging"]["next"], {})
        rows.extend(data.get("data", []))
    return rows


# ─── Database ─────────────────────────────────────────────────────────────────


def get_db_connection():
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: SUPABASE_DB_URL not set")
        sys.exit(1)
    return psycopg2.connect(db_url, connect_timeout=20)


def _coerce(row):
    """Map a Graph API insight row to RAW_TABLE column values."""
    out = {
        "account_id": str(row.get("account_id", "")),
        "account_name": row.get("account_name"),
        "date_start": row.get("date_start"),
        "date_stop": row.get("date_stop"),
    }
    for fld in NUMERIC_FIELDS:
        v = row.get(fld)
        out[fld] = float(v) if v not in (None, "") else None
    for fld in BIGINT_FIELDS:
        v = row.get(fld)
        out[fld] = int(float(v)) if v not in (None, "") else None
    for fld in JSON_FIELDS:
        v = row.get(fld)
        out[fld] = json.dumps(v) if v is not None else None
    return out


def replace_account_range(conn, account_id, start_date, end_date, rows, dry_run=False):
    """Idempotent backfill: delete the window for this account, then insert fresh.

    Avoids any dependency on a unique constraint and prevents double-counting
    when a date range is re-synced.
    """
    if dry_run:
        return len(rows)

    cur = conn.cursor()
    try:
        cur.execute(
            f"DELETE FROM {RAW_TABLE} WHERE account_id = %s "
            f"AND date_start::date BETWEEN %s AND %s",
            (account_id, start_date, end_date),
        )
        for r in rows:
            c = _coerce(r)
            cur.execute(
                f"""
                INSERT INTO {RAW_TABLE} (
                    _airbyte_raw_id, _airbyte_extracted_at, _airbyte_meta, _airbyte_generation_id,
                    account_id, account_name, date_start, date_stop,
                    spend, impressions, clicks, inline_link_clicks, reach, frequency,
                    cpc, cpm, ctr, inline_link_click_ctr, unique_link_clicks_ctr,
                    unique_inline_link_clicks, unique_inline_link_click_ctr, cost_per_unique_click,
                    actions, action_values, purchase_roas, website_purchase_roas
                ) VALUES (
                    %s, now(), %s, 0,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    str(uuid.uuid4()), json.dumps({"source": "meta_sync.py"}),
                    c["account_id"], c["account_name"], c["date_start"], c["date_stop"],
                    c["spend"], c["impressions"], c["clicks"], c["inline_link_clicks"],
                    c["reach"], c["frequency"],
                    c["cpc"], c["cpm"], c["ctr"], c["inline_link_click_ctr"],
                    c["unique_link_clicks_ctr"], c["unique_inline_link_clicks"],
                    c["unique_inline_link_click_ctr"], c["cost_per_unique_click"],
                    c["actions"], c["action_values"], c["purchase_roas"], c["website_purchase_roas"],
                ),
            )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise


# ─── Sync ─────────────────────────────────────────────────────────────────────


def _purchase_value(action_values):
    """Sum omni_purchase value from an action_values array (for the dry-run preview)."""
    if not action_values:
        return 0.0
    for a in action_values:
        if a.get("action_type") == "omni_purchase":
            return float(a.get("value", 0))
    return 0.0


def sync_account(conn, slug, account_id, token, start_date, end_date, dry_run=False):
    print(f"\n  {slug} (act_{account_id})  {start_date} -> {end_date}")
    try:
        rows = fetch_account_insights(account_id, token, start_date, end_date)
    except Exception as e:
        print(f"    ERROR fetching: {e}")
        return 0, 0.0, 0.0

    total_spend = sum(float(r.get("spend", 0) or 0) for r in rows)
    total_pv = sum(_purchase_value(r.get("action_values")) for r in rows)
    print(f"    {len(rows)} daily rows | spend ${total_spend:,.2f} | "
          f"omni_purchase ${total_pv:,.2f}", end="")

    written = replace_account_range(conn, account_id, start_date, end_date, rows, dry_run)
    print(f" -> {'(dry-run) ' if dry_run else ''}{written} rows")
    return len(rows), total_spend, total_pv


def run(start_date=None, end_date=None, client_filter=None, dry_run=False):
    load_env()

    token = os.environ.get("META_ACCESS_TOKEN")
    if not token:
        print("ERROR: META_ACCESS_TOKEN not set (add it to measurement-platform/.env)")
        sys.exit(1)

    accounts = load_meta_accounts(client_filter)
    if not accounts:
        print(f"No Meta accounts found"
              f"{' for ' + client_filter if client_filter else ''} in client_ad_accounts.csv")
        sys.exit(1)

    today = datetime.now(timezone.utc).date()
    if not end_date:
        end_date = today.isoformat()
    if not start_date:
        start_date = (today - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()

    print(f"Meta Sync - {len(accounts)} account(s), {start_date} to {end_date}")
    if dry_run:
        print("DRY RUN - no data will be written")

    conn = None if dry_run else get_db_connection()

    grand_rows = 0
    grand_spend = 0.0
    grand_pv = 0.0
    for acct in accounts:
        n, spend, pv = sync_account(
            conn, acct["slug"], acct["account_id"], token, start_date, end_date, dry_run
        )
        grand_rows += n
        grand_spend += spend
        grand_pv += pv

    if conn:
        conn.close()

    print(f"\n{'='*60}")
    print(f"DONE - {grand_rows} daily rows across {len(accounts)} account(s)")
    print(f"  Total spend:          ${grand_spend:,.2f}")
    print(f"  Total omni_purchase:  ${grand_pv:,.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Meta Marketing API data to Postgres")
    parser.add_argument("--client", help="Sync only this client slug")
    parser.add_argument("--start-date", default=None,
                        help=f"Start date YYYY-MM-DD (default: {DEFAULT_LOOKBACK_DAYS} days ago)")
    parser.add_argument("--end-date", default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    run(
        start_date=args.start_date,
        end_date=args.end_date,
        client_filter=args.client,
        dry_run=args.dry_run,
    )
