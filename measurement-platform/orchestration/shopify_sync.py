"""
shopify_sync.py — Direct Shopify Admin API sync to Postgres, replacing Airbyte.

Pulls orders for each client's Shopify store and writes them to
raw.<slug>_orders. Those tables feed stg_shopify_orders / stg_<slug>_orders
-> fact_kpi_daily (daily revenue + order count, the basis for MER).

The staging models only need created_at, total_price, and financial_status,
but this writer adapts to whatever columns each raw table actually has (so it
works against the migrated Airbyte schema without us hardcoding it).

Idempotent: delete-then-insert per store per date window.

Usage:
    python shopify_sync.py                          # default window, all stores
    python shopify_sync.py --client chubble         # one store
    python shopify_sync.py --start-date 2026-04-01  # explicit backfill start
    python shopify_sync.py --dry-run                # preview without writing

Env (measurement-platform/.env):
    SUPABASE_DB_URL       — Postgres connection string
    SHOPIFY_CLIENTS_JSON  — JSON array:
        [{"slug":"chubble","shop":"chubblegum.myshopify.com","token":"shpat_..."}, ...]
"""

import argparse
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

SHOPIFY_API_VERSION = "2025-01"
DEFAULT_LOOKBACK_DAYS = 45
PAGE_LIMIT = 250
REQUEST_INTERVAL = 0.55  # Shopify REST allows ~2 req/sec; stay under it
MAX_RETRIES = 4

# Flat order fields we request + try to store (intersected with each table's
# actual columns at runtime). Nested objects (customer, line_items) are skipped.
ORDER_FIELDS = [
    "id", "created_at", "updated_at", "processed_at",
    "total_price", "subtotal_price", "total_tax", "total_discounts",
    "financial_status", "fulfillment_status",
    "name", "order_number", "currency", "email", "test", "cancelled_at",
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


def load_shopify_clients(client_filter=None):
    raw = os.environ.get("SHOPIFY_CLIENTS_JSON", "")
    if not raw:
        print("ERROR: SHOPIFY_CLIENTS_JSON env var not set")
        sys.exit(1)
    try:
        clients = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse SHOPIFY_CLIENTS_JSON: {e}")
        sys.exit(1)
    out = []
    for c in clients:
        if not c.get("slug") or not c.get("shop") or not c.get("token"):
            print(f"WARNING: skipping invalid Shopify client entry: {c.get('slug', c)}")
            continue
        slug = c["slug"].lower()
        if client_filter and slug != client_filter.lower():
            continue
        out.append({"slug": slug, "shop": c["shop"], "token": c["token"]})
    return out


# ─── Shopify Admin API ────────────────────────────────────────────────────────

_last_request_time = 0.0


def _rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_INTERVAL:
        time.sleep(REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def _get(url, token, params=None):
    """GET the Shopify Admin API with rate limiting + retry. Returns the Response."""
    headers = {"X-Shopify-Access-Token": token, "Accept": "application/json"}
    for attempt in range(MAX_RETRIES + 1):
        _rate_limit()
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=60)
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            raise
        if resp.status_code == 200:
            return resp
        if resp.status_code == 429:  # throttled
            retry_after = float(resp.headers.get("Retry-After", 2))
            time.sleep(retry_after)
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(f"Shopify API {resp.status_code}: {resp.text[:300]}")
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries: {url}")


def _parse_next_link(link_header):
    """Extract the rel=next URL from a Shopify Link header (cursor pagination)."""
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


def fetch_orders(shop, token, start_date, end_date):
    """Fetch all orders created in [start_date, end_date] for one store."""
    base = f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}/orders.json"
    params = {
        "status": "any",
        "created_at_min": f"{start_date}T00:00:00Z",
        "created_at_max": f"{end_date}T23:59:59Z",
        "limit": PAGE_LIMIT,
        "fields": ",".join(ORDER_FIELDS),
    }
    orders = []
    resp = _get(base, token, params)
    orders.extend(resp.json().get("orders", []))
    next_url = _parse_next_link(resp.headers.get("Link"))
    while next_url:
        resp = _get(next_url, token)  # cursor is embedded in the URL
        orders.extend(resp.json().get("orders", []))
        next_url = _parse_next_link(resp.headers.get("Link"))
    return orders


# ─── Database ─────────────────────────────────────────────────────────────────


def get_db_connection():
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: SUPABASE_DB_URL not set")
        sys.exit(1)
    return psycopg2.connect(db_url, connect_timeout=20)


def table_columns(cur, schema, table):
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s",
        (schema, table),
    )
    return {r[0] for r in cur.fetchall()}


def replace_orders(conn, slug, start_date, end_date, orders, dry_run=False):
    """Delete the date window for this store, then insert fresh orders.

    Only writes columns that exist in raw.<slug>_orders (adapts to the table).
    """
    table = f"{slug}_orders"
    if dry_run:
        return len(orders)

    cur = conn.cursor()
    try:
        cols = table_columns(cur, "raw", table)
        if not cols:
            raise RuntimeError(f"raw.{table} does not exist")

        # Airbyte-style metadata always written when the column exists
        meta = {
            "_airbyte_raw_id": lambda o: str(uuid.uuid4()),
            "_airbyte_extracted_at": lambda o: datetime.now(timezone.utc),
            "_airbyte_meta": lambda o: json.dumps({"source": "shopify_sync.py"}),
            "_airbyte_generation_id": lambda o: 0,
        }
        # Flat order fields we can map directly
        data_fields = [f for f in ORDER_FIELDS if f in cols]
        meta_fields = [f for f in meta if f in cols]
        insert_cols = meta_fields + data_fields
        placeholders = ", ".join(["%s"] * len(insert_cols))
        col_sql = ", ".join(f'"{c}"' for c in insert_cols)

        cur.execute(
            f'DELETE FROM raw."{table}" WHERE created_at::date BETWEEN %s AND %s',
            (start_date, end_date),
        )
        for o in orders:
            row = [meta[c](o) for c in meta_fields] + [o.get(c) for c in data_fields]
            cur.execute(
                f'INSERT INTO raw."{table}" ({col_sql}) VALUES ({placeholders})', row
            )
        conn.commit()
        return len(orders)
    except Exception:
        conn.rollback()
        raise


# ─── Sync ─────────────────────────────────────────────────────────────────────


def _paid_revenue(orders):
    """Sum total_price of paid/partially_paid orders (for the dry-run preview)."""
    total = 0.0
    n = 0
    for o in orders:
        if o.get("financial_status") in ("paid", "partially_paid"):
            total += float(o.get("total_price") or 0)
            n += 1
    return n, total


def sync_store(conn, client, start_date, end_date, dry_run=False):
    slug = client["slug"]
    print(f"\n  {slug} ({client['shop']})  {start_date} -> {end_date}")
    try:
        orders = fetch_orders(client["shop"], client["token"], start_date, end_date)
    except Exception as e:
        print(f"    ERROR fetching: {e}")
        return 0, 0.0

    paid_n, paid_rev = _paid_revenue(orders)
    print(f"    {len(orders)} orders | {paid_n} paid | revenue ${paid_rev:,.2f}", end="")
    written = replace_orders(conn, slug, start_date, end_date, orders, dry_run)
    print(f" -> {'(dry-run) ' if dry_run else ''}{written} rows")
    return len(orders), paid_rev


def run(start_date=None, end_date=None, client_filter=None, dry_run=False):
    load_env()
    clients = load_shopify_clients(client_filter)
    if not clients:
        print(f"No Shopify stores found"
              f"{' for ' + client_filter if client_filter else ''} in SHOPIFY_CLIENTS_JSON")
        sys.exit(1)

    today = datetime.now(timezone.utc).date()
    if not end_date:
        end_date = today.isoformat()
    if not start_date:
        start_date = (today - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()

    print(f"Shopify Sync - {len(clients)} store(s), {start_date} to {end_date}")
    if dry_run:
        print("DRY RUN - no data will be written")

    conn = None if dry_run else get_db_connection()
    grand_orders = 0
    grand_rev = 0.0
    for c in clients:
        n, rev = sync_store(conn, c, start_date, end_date, dry_run)
        grand_orders += n
        grand_rev += rev
    if conn:
        conn.close()

    print(f"\n{'='*60}")
    print(f"DONE - {grand_orders} orders across {len(clients)} store(s)")
    print(f"  Paid revenue (preview): ${grand_rev:,.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync Shopify orders to Postgres")
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
