"""
ga4_sync.py — Direct GA4 Data API sync to Supabase, bypassing Airbyte.
Uses gcloud application-default credentials or service account key.

Usage:
    python ga4_sync.py                              # sync all GA4 clients
    python ga4_sync.py --property 512135208          # sync one property
    python ga4_sync.py --start-date 2025-01-26       # custom start date
    python ga4_sync.py --dry-run                     # preview without writing

Env:
    SUPABASE_DB_URL — Postgres connection string
    GOOGLE_APPLICATION_CREDENTIALS — (optional) path to service account key
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_START_DATE = "2025-01-26"

# GA4 properties to sync: {property_id: description}
# Add new properties here
GA4_PROPERTIES = {
    "512135208": "Secondkind",
}


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


# ─── GA4 Data API ─────────────────────────────────────────────────────────────


def get_ga4_client():
    """Create GA4 Data API client using available credentials.

    Priority:
    1. User OAuth credentials (ga4_user_credentials.json) — from OAuth Playground
    2. Service account key (airbyte-ga4-key.json)
    3. Application default credentials
    """
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.oauth2.credentials import Credentials

    # Priority 1: User OAuth credentials
    user_creds_path = Path(__file__).resolve().parent.parent / "ga4_user_credentials.json"
    if user_creds_path.exists():
        import json
        with open(user_creds_path) as f:
            creds_data = json.load(f)
        creds = Credentials(
            token=creds_data.get("token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=creds_data.get("client_id"),
            client_secret=creds_data.get("client_secret", ""),
            scopes=creds_data.get("scopes"),
        )
        print("  Using OAuth user credentials")
        return BetaAnalyticsDataClient(credentials=creds)

    # Priority 2: Service account key
    key_path = Path(__file__).resolve().parent.parent / "airbyte-ga4-key.json"
    if key_path.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(key_path))
        print("  Using service account key")

    return BetaAnalyticsDataClient()


def fetch_events_report(client, property_id, start_date, end_date):
    """Fetch events report: eventName, eventCount, totalUsers, totalRevenue."""
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest,
    )

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="date"), Dimension(name="eventName")],
        metrics=[
            Metric(name="eventCount"),
            Metric(name="totalUsers"),
            Metric(name="totalRevenue"),
            Metric(name="eventCountPerUser"),
        ],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        limit=100000,
    )
    response = client.run_report(request)

    rows = []
    for row in response.rows:
        rows.append({
            "date": row.dimension_values[0].value,
            "eventName": row.dimension_values[1].value,
            "eventCount": int(row.metric_values[0].value),
            "totalUsers": int(row.metric_values[1].value),
            "totalRevenue": float(row.metric_values[2].value),
            "eventCountPerUser": float(row.metric_values[3].value),
            "property_id": property_id,
        })
    return rows


def fetch_website_overview(client, property_id, start_date, end_date):
    """Fetch website overview: sessions, users, pageviews, bounce rate, etc."""
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest,
    )

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="date")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="newUsers"),
            Metric(name="totalUsers"),
            Metric(name="screenPageViews"),
            Metric(name="bounceRate"),
            Metric(name="sessionsPerUser"),
            Metric(name="averageSessionDuration"),
        ],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        limit=100000,
    )
    response = client.run_report(request)

    rows = []
    for row in response.rows:
        rows.append({
            "date": row.dimension_values[0].value,
            "sessions": int(row.metric_values[0].value),
            "newUsers": int(row.metric_values[1].value),
            "totalUsers": int(row.metric_values[2].value),
            "screenPageViews": int(row.metric_values[3].value),
            "bounceRate": float(row.metric_values[4].value),
            "sessionsPerUser": float(row.metric_values[5].value),
            "averageSessionDuration": float(row.metric_values[6].value),
            "property_id": property_id,
        })
    return rows


def fetch_traffic_report(client, property_id, start_date, end_date):
    """Fetch traffic by source/medium."""
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest,
    )

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[
            Dimension(name="date"),
            Dimension(name="sessionSource"),
            Dimension(name="sessionMedium"),
        ],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="eventCount"),
            Metric(name="totalRevenue"),
            Metric(name="engagementRate"),
        ],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        limit=100000,
    )
    response = client.run_report(request)

    rows = []
    for row in response.rows:
        rows.append({
            "date": row.dimension_values[0].value,
            "sessionSource": row.dimension_values[1].value,
            "sessionMedium": row.dimension_values[2].value,
            "sessions": int(row.metric_values[0].value),
            "totalUsers": int(row.metric_values[1].value),
            "eventCount": int(row.metric_values[2].value),
            "totalRevenue": float(row.metric_values[3].value),
            "engagementRate": float(row.metric_values[4].value),
            "property_id": property_id,
        })
    return rows


# ─── Database ─────────────────────────────────────────────────────────────────


def get_db_connection():
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: SUPABASE_DB_URL not set")
        sys.exit(1)
    return psycopg2.connect(db_url)


def upsert_events(conn, rows):
    """Upsert events report rows into raw.ga4_events_report."""
    if not rows:
        return 0
    cur = conn.cursor()
    count = 0
    for row in rows:
        cur.execute("""
            INSERT INTO raw.ga4_events_report
                (_airbyte_raw_id, _airbyte_extracted_at, _airbyte_meta, _airbyte_generation_id,
                 date, "eventName", "eventCount", "totalUsers", "totalRevenue",
                 "eventCountPerUser", property_id)
            VALUES (%s, now(), %s, 0, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, "eventName", property_id)
            DO UPDATE SET
                "eventCount" = EXCLUDED."eventCount",
                "totalUsers" = EXCLUDED."totalUsers",
                "totalRevenue" = EXCLUDED."totalRevenue",
                "eventCountPerUser" = EXCLUDED."eventCountPerUser",
                _airbyte_extracted_at = now()
        """, (
            str(uuid.uuid4()),
            json.dumps({"source": "ga4_sync.py"}),
            row["date"], row["eventName"], row["eventCount"],
            row["totalUsers"], row["totalRevenue"],
            row["eventCountPerUser"], row["property_id"],
        ))
        count += 1
    conn.commit()
    return count


def upsert_website_overview(conn, rows):
    """Upsert website overview rows into raw.ga4_website_overview."""
    if not rows:
        return 0
    cur = conn.cursor()
    count = 0
    for row in rows:
        cur.execute("""
            INSERT INTO raw.ga4_website_overview
                (_airbyte_raw_id, _airbyte_extracted_at, _airbyte_meta, _airbyte_generation_id,
                 date, sessions, "newUsers", "totalUsers", "screenPageViews",
                 "bounceRate", "sessionsPerUser", "averageSessionDuration", property_id)
            VALUES (%s, now(), %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, property_id)
            DO UPDATE SET
                sessions = EXCLUDED.sessions,
                "newUsers" = EXCLUDED."newUsers",
                "totalUsers" = EXCLUDED."totalUsers",
                "screenPageViews" = EXCLUDED."screenPageViews",
                "bounceRate" = EXCLUDED."bounceRate",
                "sessionsPerUser" = EXCLUDED."sessionsPerUser",
                "averageSessionDuration" = EXCLUDED."averageSessionDuration",
                _airbyte_extracted_at = now()
        """, (
            str(uuid.uuid4()),
            json.dumps({"source": "ga4_sync.py"}),
            row["date"], row["sessions"], row["newUsers"],
            row["totalUsers"], row["screenPageViews"],
            row["bounceRate"], row["sessionsPerUser"],
            row["averageSessionDuration"], row["property_id"],
        ))
        count += 1
    conn.commit()
    return count


def upsert_traffic(conn, rows):
    """Upsert traffic rows into raw.ga4_traffic_acquisition_session_source_medium_report."""
    if not rows:
        return 0
    cur = conn.cursor()
    count = 0
    for row in rows:
        cur.execute("""
            INSERT INTO raw.ga4_traffic_acquisition_session_source_medium_report
                (_airbyte_raw_id, _airbyte_extracted_at, _airbyte_meta, _airbyte_generation_id,
                 date, "sessionSource", "sessionMedium", sessions, "totalUsers",
                 "eventCount", "totalRevenue", "engagementRate", property_id)
            VALUES (%s, now(), %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, "sessionSource", "sessionMedium", property_id)
            DO UPDATE SET
                sessions = EXCLUDED.sessions,
                "totalUsers" = EXCLUDED."totalUsers",
                "eventCount" = EXCLUDED."eventCount",
                "totalRevenue" = EXCLUDED."totalRevenue",
                "engagementRate" = EXCLUDED."engagementRate",
                _airbyte_extracted_at = now()
        """, (
            str(uuid.uuid4()),
            json.dumps({"source": "ga4_sync.py"}),
            row["date"], row["sessionSource"], row["sessionMedium"],
            row["sessions"], row["totalUsers"],
            row["eventCount"], row["totalRevenue"],
            row["engagementRate"], row["property_id"],
        ))
        count += 1
    conn.commit()
    return count


def ensure_unique_constraints(conn):
    """Add unique constraints if they don't exist (for upsert ON CONFLICT)."""
    cur = conn.cursor()
    constraints = [
        ("ga4_events_uq", "raw.ga4_events_report", "(date, \"eventName\", property_id)"),
        ("ga4_overview_uq", "raw.ga4_website_overview", "(date, property_id)"),
        ("ga4_traffic_uq", "raw.ga4_traffic_acquisition_session_source_medium_report",
         "(date, \"sessionSource\", \"sessionMedium\", property_id)"),
    ]
    for name, table, cols in constraints:
        cur.execute(f"""
            DO $$ BEGIN
                ALTER TABLE {table} ADD CONSTRAINT {name} UNIQUE {cols};
            EXCEPTION WHEN duplicate_table THEN NULL;
            END $$
        """)
    conn.commit()


# ─── Sync Logic ───────────────────────────────────────────────────────────────


def sync_property(client, conn, property_id, description, start_date, end_date, dry_run=False):
    """Sync all GA4 reports for one property."""
    print(f"\n{'='*60}")
    print(f"Syncing: {description} (property {property_id})")
    print(f"  Date range: {start_date} to {end_date}")

    # Events report
    print(f"\n  --- Events Report ---")
    print(f"    Fetching...", end=" ", flush=True)
    try:
        events = fetch_events_report(client, property_id, start_date, end_date)
        print(f"{len(events)} rows", end="")
        if not dry_run and events:
            count = upsert_events(conn, events)
            print(f" -> {count} upserted")
        else:
            print()
    except Exception as e:
        print(f"ERROR: {e}")
        events = []

    # Website overview
    print(f"\n  --- Website Overview ---")
    print(f"    Fetching...", end=" ", flush=True)
    try:
        overview = fetch_website_overview(client, property_id, start_date, end_date)
        print(f"{len(overview)} rows", end="")
        if not dry_run and overview:
            count = upsert_website_overview(conn, overview)
            print(f" -> {count} upserted")
        else:
            print()
    except Exception as e:
        print(f"ERROR: {e}")
        overview = []

    # Traffic report
    print(f"\n  --- Traffic Sources ---")
    print(f"    Fetching...", end=" ", flush=True)
    try:
        traffic = fetch_traffic_report(client, property_id, start_date, end_date)
        print(f"{len(traffic)} rows", end="")
        if not dry_run and traffic:
            count = upsert_traffic(conn, traffic)
            print(f" -> {count} upserted")
        else:
            print()
    except Exception as e:
        print(f"ERROR: {e}")
        traffic = []

    total = len(events) + len(overview) + len(traffic)
    print(f"\n  Total: {total} rows ({len(events)} events, {len(overview)} overview, {len(traffic)} traffic)")
    return total


def sync_all(start_date=None, end_date=None, property_filter=None, dry_run=False):
    """Sync all configured GA4 properties."""
    load_env()

    if not start_date:
        start_date = DEFAULT_START_DATE
    if not end_date:
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    properties = GA4_PROPERTIES
    if property_filter:
        properties = {k: v for k, v in properties.items() if k == property_filter}
        if not properties:
            print(f"ERROR: Property '{property_filter}' not found")
            sys.exit(1)

    print(f"GA4 Sync — {len(properties)} properties, {start_date} to {end_date}")
    if dry_run:
        print("DRY RUN — no data will be written")

    client = get_ga4_client()
    conn = None if dry_run else get_db_connection()

    if conn:
        ensure_unique_constraints(conn)

    grand_total = 0
    for prop_id, description in properties.items():
        total = sync_property(client, conn, prop_id, description, start_date, end_date, dry_run)
        grand_total += total

    if conn:
        conn.close()

    print(f"\n{'='*60}")
    print(f"DONE — {grand_total} total rows across {len(properties)} properties")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync GA4 data to Supabase")
    parser.add_argument("--property", help="Sync only this property ID")
    parser.add_argument("--start-date", default=None, help=f"Start date (default: {DEFAULT_START_DATE})")
    parser.add_argument("--end-date", default=None, help="End date (default: today)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    sync_all(
        start_date=args.start_date,
        end_date=args.end_date,
        property_filter=args.property,
        dry_run=args.dry_run,
    )
