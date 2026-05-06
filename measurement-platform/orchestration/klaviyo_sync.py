"""
klaviyo_sync.py — Direct Klaviyo API sync to Supabase, replacing Airbyte's slow connector.
Fetches campaign_values_reports and flow_series_reports for multiple clients.

Usage:
    python klaviyo_sync.py                          # sync all clients
    python klaviyo_sync.py --client expand          # sync one client
    python klaviyo_sync.py --start-date 2025-10-01  # custom start date
    python klaviyo_sync.py --dry-run                # preview without writing

Env:
    SUPABASE_DB_URL — Postgres connection string
    KLAVIYO_CLIENTS_JSON — JSON array: [{"slug":"expand","api_key":"pk_..."},...]
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
import requests

# ─── Configuration ────────────────────────────────────────────────────────────

KLAVIYO_BASE_URL = "https://a.klaviyo.com/api"
KLAVIYO_REVISION = "2025-01-15"
DEFAULT_START_DATE = "2025-04-01"
RATE_LIMIT_RPM = 30
REQUEST_INTERVAL = 60.0 / RATE_LIMIT_RPM
MAX_RETRIES = 3


def load_env():
    """Load .env file from the measurement-platform directory."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())


def load_client_configs():
    """Load Klaviyo client configs from KLAVIYO_CLIENTS_JSON env var."""
    raw = os.environ.get("KLAVIYO_CLIENTS_JSON", "")
    if not raw:
        print("ERROR: KLAVIYO_CLIENTS_JSON env var not set")
        sys.exit(1)
    try:
        clients = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse KLAVIYO_CLIENTS_JSON: {e}")
        sys.exit(1)
    validated = []
    for c in clients:
        if not c.get("slug") or not c.get("api_key"):
            print(f"WARNING: Skipping invalid client entry: {c}")
            continue
        validated.append({"slug": c["slug"].lower(), "api_key": c["api_key"]})
    return validated


# ─── Klaviyo API ──────────────────────────────────────────────────────────────

_last_request_time = 0.0


def _rate_limit():
    """Enforce rate limiting between API calls."""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < REQUEST_INTERVAL:
        time.sleep(REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def _api_headers(api_key):
    return {
        "Authorization": f"Klaviyo-API-Key {api_key}",
        "revision": KLAVIYO_REVISION,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _api_post(api_key, endpoint, body):
    """POST to Klaviyo API with rate limiting and retry."""
    url = f"{KLAVIYO_BASE_URL}/{endpoint}"
    headers = _api_headers(api_key)

    for attempt in range(MAX_RETRIES + 1):
        _rate_limit()
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=120)
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt
                print(f"    Request error, retrying in {wait}s: {e}")
                time.sleep(wait)
                continue
            raise

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            print(f"    Rate limited, waiting {retry_after}s...")
            time.sleep(retry_after)
            continue
        elif resp.status_code >= 500:
            wait = 2 ** attempt
            print(f"    Server error {resp.status_code}, retrying in {wait}s...")
            time.sleep(wait)
            continue
        else:
            error_text = resp.text[:300]
            print(f"    API error {resp.status_code}: {error_text}")
            raise RuntimeError(f"API {resp.status_code}: {error_text}")

    raise RuntimeError(f"Failed after {MAX_RETRIES} retries: {endpoint}")


def get_placed_order_metric_id(api_key):
    """Find a 'Placed Order' metric ID that supports reporting.

    Some accounts have multiple 'Placed Order' metrics from different
    integrations (Shopify, WooCommerce). Not all support the reporting
    API. We prefer Klaviyo-native or API-sourced metrics over ecommerce
    platform metrics, and fall back to 'Ordered Product' if needed.
    """
    _rate_limit()
    resp = requests.get(
        f"{KLAVIYO_BASE_URL}/metrics",
        headers=_api_headers(api_key),
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"    WARNING: Could not fetch metrics ({resp.status_code})")
        return None

    metrics = resp.json().get("data", [])

    # Collect candidates: prefer native/API metrics, then ecommerce
    candidates = []
    for m in metrics:
        name = m["attributes"]["name"].lower()
        integration = m["attributes"].get("integration", {}).get("name", "").lower()
        if name in ("placed order", "ordered product"):
            # Prioritize: klaviyo/api > woocommerce > shopify
            priority = 0 if integration in ("klaviyo", "api", "") else (1 if "woocommerce" in integration else 2)
            candidates.append((priority, m["id"], m["attributes"]["name"], integration))

    candidates.sort()
    if candidates:
        chosen = candidates[0]
        if len(candidates) > 1:
            print(f"({len(candidates)} candidates, chose {chosen[2]} via {chosen[3] or 'native'})", end=" ")
        return chosen[1]

    print("    WARNING: No 'Placed Order' metric found")
    return None


def fetch_campaign_values(api_key, start_date, end_date, conversion_metric_id=None):
    """Fetch campaign values reports from Klaviyo."""
    # Stats that require a conversion metric
    conversion_stats = [
        "conversion_value",
        "conversions",
        "revenue_per_recipient",
        "conversion_rate",
    ]
    # Stats that always work
    base_stats = [
        "delivered",
        "opens",
        "clicks",
        "bounced",
        "failed",
        "unsubscribes",
        "open_rate",
        "click_rate",
        "spam_complaints",
        "delivery_rate",
        "recipients",
        "unsubscribe_rate",
        "bounce_rate",
        "click_to_open_rate",
    ]
    stats = base_stats + (conversion_stats if conversion_metric_id else [])

    attributes = {
        "statistics": stats,
        "timeframe": {
            "start": f"{start_date}T00:00:00+00:00",
            "end": f"{end_date}T00:00:00+00:00",
        },
        "filter": "equals(send_channel,'email')",
    }
    if conversion_metric_id:
        attributes["conversion_metric_id"] = conversion_metric_id

    body = {"data": {"type": "campaign-values-report", "attributes": attributes}}
    return _api_post(api_key, "campaign-values-reports", body)


def fetch_flow_series(api_key, start_date, end_date, conversion_metric_id=None):
    """Fetch flow series reports from Klaviyo."""
    conversion_stats = [
        "conversions",
        "conversion_value",
        "revenue_per_recipient",
    ]
    base_stats = [
        "delivered",
        "opens",
        "clicks",
        "bounced",
        "failed",
        "unsubscribes",
        "recipients",
        "spam_complaints",
    ]
    stats = base_stats + (conversion_stats if conversion_metric_id else [])

    attributes = {
        "statistics": stats,
        "timeframe": {
            "start": f"{start_date}T00:00:00+00:00",
            "end": f"{end_date}T00:00:00+00:00",
        },
        "interval": "monthly",
        "filter": "equals(send_channel,'email')",
    }
    if conversion_metric_id:
        attributes["conversion_metric_id"] = conversion_metric_id

    body = {"data": {"type": "flow-series-report", "attributes": attributes}}
    return _api_post(api_key, "flow-series-reports", body)


# ─── Database ─────────────────────────────────────────────────────────────────


def get_db_connection():
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: SUPABASE_DB_URL not set")
        sys.exit(1)
    return psycopg2.connect(db_url)


def create_tables(conn, slug):
    """Create raw tables for a client if they don't exist."""
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS raw")

    # Campaign values reports
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS raw.{slug}_klaviyo_campaign_values_reports (
            _airbyte_raw_id        UUID DEFAULT gen_random_uuid() PRIMARY KEY,
            _airbyte_extracted_at  TIMESTAMPTZ DEFAULT now(),
            _airbyte_meta          JSONB DEFAULT '{{"source": "klaviyo_sync.py"}}',
            _airbyte_generation_id BIGINT DEFAULT 0 NOT NULL,
            date                   TIMESTAMPTZ,
            groupings              JSONB,
            statistics             JSONB,
            campaign_id            TEXT,
            send_channel           TEXT,
            campaign_message_id    TEXT,
            conversion_metric_id   TEXT
        )
    """)

    # Add unique constraint if not exists
    cur.execute(f"""
        DO $$ BEGIN
            ALTER TABLE raw.{slug}_klaviyo_campaign_values_reports
                ADD CONSTRAINT {slug}_campaign_values_uq UNIQUE (date, campaign_id, conversion_metric_id);
        EXCEPTION WHEN duplicate_table THEN NULL;
        END $$
    """)

    # Flow series reports
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS raw.{slug}_klaviyo_flow_series_reports (
            _airbyte_raw_id        UUID DEFAULT gen_random_uuid() PRIMARY KEY,
            _airbyte_extracted_at  TIMESTAMPTZ DEFAULT now(),
            _airbyte_meta          JSONB DEFAULT '{{"source": "klaviyo_sync.py"}}',
            _airbyte_generation_id BIGINT DEFAULT 0,
            date                   TIMESTAMPTZ,
            flow_id                TEXT,
            groupings              JSONB,
            statistics             JSONB,
            send_channel           TEXT,
            flow_message_id        TEXT,
            conversion_metric_id   TEXT
        )
    """)

    cur.execute(f"""
        DO $$ BEGIN
            ALTER TABLE raw.{slug}_klaviyo_flow_series_reports
                ADD CONSTRAINT {slug}_flow_series_uq UNIQUE (date, flow_id, flow_message_id, conversion_metric_id);
        EXCEPTION WHEN duplicate_table THEN NULL;
        END $$
    """)

    conn.commit()


def upsert_campaign_rows(conn, slug, rows):
    """Upsert campaign values rows into the database."""
    if not rows:
        return 0
    table = f"raw.{slug}_klaviyo_campaign_values_reports"
    cur = conn.cursor()
    count = 0
    for row in rows:
        try:
            cur.execute(
                f"""
                INSERT INTO {table}
                    (_airbyte_raw_id, _airbyte_extracted_at, _airbyte_meta, _airbyte_generation_id,
                     date, groupings, statistics,
                     campaign_id, send_channel, campaign_message_id, conversion_metric_id)
                VALUES (%s, now(), %s, 0, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date, campaign_id, conversion_metric_id) DO UPDATE SET
                    statistics = EXCLUDED.statistics,
                    groupings = EXCLUDED.groupings,
                    _airbyte_extracted_at = now()
                """,
                (
                    str(uuid.uuid4()),
                    json.dumps({"source": "klaviyo_sync.py"}),
                    row.get("date"),
                    json.dumps(row.get("groupings", {})),
                    json.dumps(row.get("statistics", {})),
                    row.get("campaign_id", ""),
                    row.get("send_channel", "email"),
                    row.get("campaign_message_id", ""),
                    row.get("conversion_metric_id", ""),
                ),
            )
            count += 1
        except Exception as e:
            conn.rollback()
            print(f"\n    Row insert error: {e}")
    conn.commit()
    return count


def upsert_flow_rows(conn, slug, rows):
    """Upsert flow series rows into the database."""
    if not rows:
        return 0
    table = f"raw.{slug}_klaviyo_flow_series_reports"
    cur = conn.cursor()
    count = 0
    for row in rows:
        try:
            cur.execute(
                f"""
                INSERT INTO {table}
                    (_airbyte_raw_id, _airbyte_extracted_at, _airbyte_meta, _airbyte_generation_id,
                     date, flow_id, groupings,
                     statistics, send_channel, flow_message_id, conversion_metric_id)
                VALUES (%s, now(), %s, 0, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date, flow_id, flow_message_id, conversion_metric_id) DO UPDATE SET
                    statistics = EXCLUDED.statistics,
                    groupings = EXCLUDED.groupings,
                    _airbyte_extracted_at = now()
                """,
                (
                    str(uuid.uuid4()),
                    json.dumps({"source": "klaviyo_sync.py"}),
                    row.get("date"),
                    row.get("flow_id", ""),
                    json.dumps(row.get("groupings", {})),
                    json.dumps(row.get("statistics", {})),
                    row.get("send_channel", "email"),
                    row.get("flow_message_id", ""),
                    row.get("conversion_metric_id", ""),
                ),
            )
            count += 1
        except Exception as e:
            conn.rollback()
            print(f"\n    Row insert error: {e}")
    conn.commit()
    return count


def _get_all_order_metric_ids(api_key):
    """Return all 'Placed Order'/'Ordered Product' metric IDs, priority-sorted."""
    _rate_limit()
    resp = requests.get(
        f"{KLAVIYO_BASE_URL}/metrics",
        headers=_api_headers(api_key),
        timeout=30,
    )
    if resp.status_code != 200:
        return []
    ids = []
    for m in resp.json().get("data", []):
        name = m["attributes"]["name"].lower()
        integration = m["attributes"].get("integration", {}).get("name", "").lower()
        if name in ("placed order", "ordered product"):
            priority = 0 if integration in ("klaviyo", "api", "") else (1 if "woocommerce" in integration else 2)
            ids.append((priority, m["id"]))
    ids.sort()
    return [mid for _, mid in ids]


# ─── Response Parsing ─────────────────────────────────────────────────────────


def parse_campaign_values_response(data, timeframe_start, conversion_metric_id):
    """Parse Klaviyo campaign-values-reports response into rows."""
    rows = []
    results = data.get("data", {}).get("attributes", {}).get("results", [])
    for result in results:
        groupings = result.get("groupings", {})
        statistics = result.get("statistics", {})
        rows.append({
            "date": timeframe_start,
            "campaign_id": groupings.get("campaign_id", ""),
            "send_channel": groupings.get("send_channel", "email"),
            "campaign_message_id": groupings.get("campaign_message_id", ""),
            "conversion_metric_id": conversion_metric_id,
            "groupings": groupings,
            "statistics": statistics,
        })
    return rows


def parse_flow_series_response(data, timeframe_start, conversion_metric_id):
    """Parse Klaviyo flow-series-reports response into rows."""
    rows = []
    results = data.get("data", {}).get("attributes", {}).get("results", [])
    for result in results:
        groupings = result.get("groupings", {})
        statistics = result.get("statistics", {})
        rows.append({
            "date": result.get("date") or timeframe_start,
            "flow_id": groupings.get("flow_id", ""),
            "send_channel": groupings.get("send_channel", "email"),
            "flow_message_id": groupings.get("flow_message_id", ""),
            "conversion_metric_id": conversion_metric_id,
            "groupings": groupings,
            "statistics": statistics,
        })
    return rows


# ─── Sync Logic ───────────────────────────────────────────────────────────────


def month_chunks(start_date, end_date):
    """Generate (start, end) tuples for each month in the range."""
    from datetime import date as dt_date

    current = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    chunks = []
    while current < end:
        # End of current month
        if current.month == 12:
            next_month = dt_date(current.year + 1, 1, 1)
        else:
            next_month = dt_date(current.year, current.month + 1, 1)
        chunk_end = min(next_month, end)
        chunks.append((current.isoformat(), chunk_end.isoformat()))
        current = next_month
    return chunks


def sync_client(slug, api_key, start_date, end_date, dry_run=False):
    """Sync campaign values and flow series for one client."""
    print(f"\n{'='*60}")
    print(f"Syncing: {slug}")
    print(f"  Date range: {start_date} to {end_date}")

    chunks = month_chunks(start_date, end_date)
    print(f"  Monthly chunks: {len(chunks)}")

    conn = None if dry_run else get_db_connection()

    if not dry_run:
        create_tables(conn, slug)

    # Look up this account's "Placed Order" metric ID
    print(f"  Looking up conversion metric...", end=" ", flush=True)
    metric_id = get_placed_order_metric_id(api_key)
    # Also collect all candidate metric IDs for fallback
    _all_metric_ids = _get_all_order_metric_ids(api_key)
    print(f"using {metric_id}" if metric_id else "none found")

    total_campaign_rows = 0
    total_flow_rows = 0

    # Campaign values
    print(f"\n  --- Campaign Values Reports ---")
    campaign_metric_id = metric_id  # May be cleared on first error
    for chunk_start, chunk_end in chunks:
        print(f"    Fetching {chunk_start} to {chunk_end}...", end=" ", flush=True)
        try:
            data = fetch_campaign_values(api_key, chunk_start, chunk_end, campaign_metric_id)
            rows = parse_campaign_values_response(data, f"{chunk_start}T00:00:00+00:00", campaign_metric_id or "")
            print(f"{len(rows)} rows", end="")
            if not dry_run and rows:
                count = upsert_campaign_rows(conn, slug, rows)
                print(f" -> {count} upserted")
            else:
                print()
            total_campaign_rows += len(rows)
        except Exception as e:
            if "does not support querying" in str(e) and campaign_metric_id:
                # Try next candidate metric
                remaining = [m for m in _all_metric_ids if m != campaign_metric_id]
                if remaining:
                    campaign_metric_id = remaining[0]
                    print(f"metric unsupported, trying {campaign_metric_id}...")
                    try:
                        data = fetch_campaign_values(api_key, chunk_start, chunk_end, campaign_metric_id)
                        rows = parse_campaign_values_response(data, f"{chunk_start}T00:00:00+00:00", campaign_metric_id)
                        print(f"    {len(rows)} rows", end="")
                        if not dry_run and rows:
                            count = upsert_campaign_rows(conn, slug, rows)
                            print(f" -> {count} upserted")
                        else:
                            print()
                        total_campaign_rows += len(rows)
                    except Exception as e2:
                        print(f"ERROR: {e2}")
                        campaign_metric_id = None
                else:
                    print(f"no alternative metrics available")
                    campaign_metric_id = None
            else:
                print(f"ERROR: {e}")

    # Flow series — use same metric fallback as campaigns
    flow_metric_id = campaign_metric_id
    print(f"\n  --- Flow Series Reports ---")
    for chunk_start, chunk_end in chunks:
        print(f"    Fetching {chunk_start} to {chunk_end}...", end=" ", flush=True)
        try:
            data = fetch_flow_series(api_key, chunk_start, chunk_end, flow_metric_id)
            rows = parse_flow_series_response(data, f"{chunk_start}T00:00:00+00:00", flow_metric_id or "")
            print(f"{len(rows)} rows", end="")
            if not dry_run and rows:
                count = upsert_flow_rows(conn, slug, rows)
                print(f" -> {count} upserted")
            else:
                print()
            total_flow_rows += len(rows)
        except Exception as e:
            if "does not support querying" in str(e) and flow_metric_id:
                remaining = [m for m in _all_metric_ids if m != flow_metric_id]
                if remaining:
                    flow_metric_id = remaining[0]
                    print(f"metric unsupported, trying {flow_metric_id}...")
                    try:
                        data = fetch_flow_series(api_key, chunk_start, chunk_end, flow_metric_id)
                        rows = parse_flow_series_response(data, f"{chunk_start}T00:00:00+00:00", flow_metric_id)
                        print(f"    {len(rows)} rows", end="")
                        if not dry_run and rows:
                            count = upsert_flow_rows(conn, slug, rows)
                            print(f" -> {count} upserted")
                        else:
                            print()
                        total_flow_rows += len(rows)
                    except Exception as e2:
                        print(f"ERROR: {e2}")
                        flow_metric_id = None
                else:
                    print(f"no alternative metrics available")
                    flow_metric_id = None
            else:
                print(f"ERROR: {e}")

    if conn:
        conn.close()

    print(f"\n  Total: {total_campaign_rows} campaign rows, {total_flow_rows} flow rows")
    return total_campaign_rows, total_flow_rows


def sync_all_clients(start_date=None, end_date=None, client_filter=None, dry_run=False):
    """Sync all configured Klaviyo clients."""
    load_env()
    clients = load_client_configs()

    if not start_date:
        start_date = DEFAULT_START_DATE
    if not end_date:
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if client_filter:
        clients = [c for c in clients if c["slug"] == client_filter.lower()]
        if not clients:
            print(f"ERROR: Client '{client_filter}' not found in KLAVIYO_CLIENTS_JSON")
            sys.exit(1)

    print(f"Klaviyo Sync — {len(clients)} clients, {start_date} to {end_date}")
    if dry_run:
        print("DRY RUN — no data will be written")

    grand_campaigns = 0
    grand_flows = 0

    for client in clients:
        campaigns, flows = sync_client(
            client["slug"], client["api_key"], start_date, end_date, dry_run
        )
        grand_campaigns += campaigns
        grand_flows += flows

    print(f"\n{'='*60}")
    print(f"DONE — {grand_campaigns} campaign rows, {grand_flows} flow rows across {len(clients)} clients")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Klaviyo data to Supabase")
    parser.add_argument("--client", help="Sync only this client slug")
    parser.add_argument("--start-date", default=None, help=f"Start date (default: {DEFAULT_START_DATE})")
    parser.add_argument("--end-date", default=None, help="End date (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    sync_all_clients(
        start_date=args.start_date,
        end_date=args.end_date,
        client_filter=args.client,
        dry_run=args.dry_run,
    )
