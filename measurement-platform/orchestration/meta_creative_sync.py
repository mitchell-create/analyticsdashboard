"""
meta_creative_sync.py — Direct Meta Marketing API sync of AD-LEVEL daily insights.

Where meta_sync.py pulls account-level totals, this pulls per-ad daily metrics so
we can analyze CREATIVE performance: which angles / hooks / formats work, and
where in the creative funnel (hook -> hold -> click -> add-to-cart -> purchase)
each one wins or loses. See INSIGHTS_PLAYBOOK.md §4.3.

The ad NAME carries the naming convention (angle / hook / format / ...). We land
it raw here and parse it downstream in dbt (stg_meta_ad_creative), so the
convention can change without touching this sync.

Writes to raw.meta_ad_insights_daily
(see warehouse/schema/070_raw_meta_ad_insights.sql). Idempotent: delete-then-
insert per account / date window. Daily granularity so creative fatigue
(CTR / hook-rate decay vs frequency) is visible over time.

Ad-level volume can be large, so each account's window is fetched in weekly chunks
(+ pagination) to stay within synchronous-insights limits.

Usage:
    python meta_creative_sync.py
    python meta_creative_sync.py --client expand
    python meta_creative_sync.py --start-date 2026-05-15
    python meta_creative_sync.py --dry-run

Env (measurement-platform/.env):
    SUPABASE_DB_URL    — Postgres connection string
    META_ACCESS_TOKEN  — System User access token (EAA...)
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import requests

# ─── Configuration ────────────────────────────────────────────────────────────

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
RAW_TABLE = "raw.meta_ad_insights_daily"

DEFAULT_LOOKBACK_DAYS = 30
CHUNK_DAYS = 7  # fetch each account's window in weekly chunks (ad-level volume guard)
RATE_LIMIT_RPM = 25
REQUEST_INTERVAL = 60.0 / RATE_LIMIT_RPM
MAX_RETRIES = 4

# Fields requested at level=ad, daily. Video fields drive hook/hold rates.
INSIGHT_FIELDS = [
    "account_id",
    "campaign_id", "campaign_name",
    "adset_id", "adset_name",
    "ad_id", "ad_name",
    "spend", "impressions", "reach", "frequency",
    "clicks", "inline_link_clicks", "ctr", "inline_link_click_ctr",
    "cpc", "cpm",
    "actions", "action_values",
    "video_3_sec_watched_actions",
    "video_thruplay_watched_actions",
    "video_p100_watched_actions",
    "video_avg_time_watched_actions",
]


def load_env():
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
    for attempt in range(MAX_RETRIES + 1):
        _rate_limit()
        try:
            resp = requests.get(url, params=params, timeout=180)
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                print(f"    request error, retrying: {e}")
                time.sleep(2 ** attempt)
                continue
            raise
        if resp.status_code == 200:
            return resp.json()
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
        raise RuntimeError(f"Graph API {resp.status_code}: {err.get('message', resp.text[:300])}")
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries: {url}")


def _date_chunks(start_date, end_date, days=CHUNK_DAYS):
    s = datetime.strptime(start_date, "%Y-%m-%d").date()
    e = datetime.strptime(end_date, "%Y-%m-%d").date()
    cur = s
    while cur <= e:
        chunk_end = min(cur + timedelta(days=days - 1), e)
        yield cur.isoformat(), chunk_end.isoformat()
        cur = chunk_end + timedelta(days=1)


def fetch_ad_insights(account_id, token, start_date, end_date):
    """Per-ad daily insights for one account, fetched in weekly chunks + paged."""
    rows = []
    for c_start, c_end in _date_chunks(start_date, end_date):
        url = f"{GRAPH_BASE_URL}/act_{account_id}/insights"
        params = {
            "level": "ad",
            "time_increment": 1,
            "fields": ",".join(INSIGHT_FIELDS),
            "time_range": json.dumps({"since": c_start, "until": c_end}),
            "limit": 500,
            "access_token": token,
        }
        data = _api_get(url, params)
        rows.extend(data.get("data", []))
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


def _sum_av(arr):
    """Sum the numeric `value` across an action-style array (count metrics)."""
    if not arr:
        return None
    try:
        return int(sum(float(a.get("value", 0) or 0) for a in arr))
    except (TypeError, ValueError):
        return None


def _first_av(arr):
    """First `value` from an action-style array (averages, e.g. avg watch time)."""
    if not arr:
        return None
    try:
        return float(arr[0].get("value", 0) or 0)
    except (TypeError, ValueError, IndexError):
        return None


def _num(v):
    return float(v) if v not in (None, "") else None


def _int(v):
    return int(float(v)) if v not in (None, "") else None


COLUMNS = [
    "account_id", "campaign_id", "campaign_name", "adset_id", "adset_name",
    "ad_id", "ad_name", "date_start", "date_stop",
    "spend", "impressions", "reach", "frequency",
    "clicks", "inline_link_clicks", "ctr", "inline_link_click_ctr", "cpc", "cpm",
    "video_3s_views", "video_thruplays", "video_p100_views", "video_avg_seconds",
    "actions", "action_values",
]


def _coerce(row):
    return {
        "account_id": str(row.get("account_id", "")),
        "campaign_id": row.get("campaign_id"),
        "campaign_name": row.get("campaign_name"),
        "adset_id": row.get("adset_id"),
        "adset_name": row.get("adset_name"),
        "ad_id": str(row.get("ad_id", "")),
        "ad_name": row.get("ad_name"),
        "date_start": row.get("date_start"),
        "date_stop": row.get("date_stop"),
        "spend": _num(row.get("spend")),
        "impressions": _int(row.get("impressions")),
        "reach": _int(row.get("reach")),
        "frequency": _num(row.get("frequency")),
        "clicks": _int(row.get("clicks")),
        "inline_link_clicks": _int(row.get("inline_link_clicks")),
        "ctr": _num(row.get("ctr")),
        "inline_link_click_ctr": _num(row.get("inline_link_click_ctr")),
        "cpc": _num(row.get("cpc")),
        "cpm": _num(row.get("cpm")),
        "video_3s_views": _sum_av(row.get("video_3_sec_watched_actions")),
        "video_thruplays": _sum_av(row.get("video_thruplay_watched_actions")),
        "video_p100_views": _sum_av(row.get("video_p100_watched_actions")),
        "video_avg_seconds": _first_av(row.get("video_avg_time_watched_actions")),
        "actions": json.dumps(row["actions"]) if row.get("actions") is not None else None,
        "action_values": json.dumps(row["action_values"]) if row.get("action_values") is not None else None,
    }


def replace_account_range(conn, account_id, start_date, end_date, rows, dry_run=False):
    """Idempotent backfill: delete the window for this account, then insert fresh."""
    if dry_run:
        return len(rows)
    cur = conn.cursor()
    try:
        cur.execute(
            f"DELETE FROM {RAW_TABLE} WHERE account_id = %s "
            f"AND date_start::date BETWEEN %s AND %s",
            (account_id, start_date, end_date),
        )
        placeholders = ", ".join(["%s"] * len(COLUMNS))
        col_sql = ", ".join(COLUMNS)
        written = 0
        for r in rows:
            c = _coerce(r)
            if not c["ad_id"]:
                continue  # level=ad always has an ad_id; skip any malformed row
            cur.execute(
                f"INSERT INTO {RAW_TABLE} ({col_sql}) VALUES ({placeholders})",
                [c[col] for col in COLUMNS],
            )
            written += 1
        conn.commit()
        return written
    except Exception:
        conn.rollback()
        raise


# ─── Sync ─────────────────────────────────────────────────────────────────────

def _purchase_value(action_values):
    if not action_values:
        return 0.0
    for a in action_values:
        if a.get("action_type") == "omni_purchase":
            return float(a.get("value", 0) or 0)
    return 0.0


def sync_account(conn, slug, account_id, token, start_date, end_date, dry_run=False):
    print(f"\n  {slug} (act_{account_id})  {start_date} -> {end_date}")
    try:
        rows = fetch_ad_insights(account_id, token, start_date, end_date)
    except Exception as e:
        print(f"    ERROR fetching: {e}")
        return 0, 0, 0.0
    ads = {r.get("ad_id") for r in rows if r.get("ad_id")}
    spend = sum(float(r.get("spend", 0) or 0) for r in rows)
    pv = sum(_purchase_value(r.get("action_values")) for r in rows)
    print(f"    {len(rows)} ad-day rows | {len(ads)} ads | spend ${spend:,.2f} | "
          f"omni_purchase ${pv:,.2f}", end="")
    written = replace_account_range(conn, account_id, start_date, end_date, rows, dry_run)
    print(f" -> {'(dry-run) ' if dry_run else ''}{written} rows")
    return len(ads), len(rows), spend


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

    print(f"Meta Creative (ad-level) Sync - {len(accounts)} account(s), {start_date} to {end_date}")
    if dry_run:
        print("DRY RUN - no data will be written")

    conn = None if dry_run else get_db_connection()
    grand_ads, grand_rows, grand_spend = 0, 0, 0.0
    for acct in accounts:
        n_ads, n_rows, spend = sync_account(
            conn, acct["slug"], acct["account_id"], token, start_date, end_date, dry_run
        )
        grand_ads += n_ads
        grand_rows += n_rows
        grand_spend += spend
    if conn:
        conn.close()

    print(f"\n{'='*60}")
    print(f"DONE - {grand_rows} ad-day rows across {grand_ads} ads, {len(accounts)} account(s)")
    print(f"  Total spend: ${grand_spend:,.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Meta ad-level (creative) insights to Postgres")
    parser.add_argument("--client", help="Sync only this client slug")
    parser.add_argument("--start-date", default=None,
                        help=f"Start date YYYY-MM-DD (default: {DEFAULT_LOOKBACK_DAYS} days ago)")
    parser.add_argument("--end-date", default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    run(start_date=args.start_date, end_date=args.end_date,
        client_filter=args.client, dry_run=args.dry_run)
