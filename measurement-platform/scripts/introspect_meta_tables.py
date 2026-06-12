"""Introspect the Meta raw tables: columns + date coverage. Read-only."""
import os
from pathlib import Path
import psycopg2


def load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    load_env()
    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=20)
    cur = conn.cursor()

    for tbl in ("meta_ads_insights", "meta_customaccount_insights_daily"):
        print(f"\n{'='*70}\n=== raw.{tbl} ===")
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='raw' AND table_name=%s
            ORDER BY ordinal_position
        """, (tbl,))
        cols = cur.fetchall()
        for name, dtype in cols:
            print(f"  {name:<40} {dtype}")

        # Date coverage + row count
        colnames = [c[0] for c in cols]
        if "date_start" in colnames:
            cur.execute(f"SELECT MIN(date_start::date), MAX(date_start::date), COUNT(*) FROM raw.{tbl}")
            lo, hi, n = cur.fetchone()
            print(f"  --> date_start range: {lo} to {hi}, {n:,} rows")
        # distinct account_ids
        if "account_id" in colnames:
            cur.execute(f"SELECT account_id, COUNT(*) FROM raw.{tbl} GROUP BY account_id ORDER BY 2 DESC LIMIT 10")
            print(f"  --> account_id distribution:")
            for acct, cnt in cur.fetchall():
                print(f"        {acct}: {cnt:,}")

    # Sample one row of each to see actual JSON shapes
    print(f"\n{'='*70}\n=== Sample action_values from meta_customaccount_insights_daily ===")
    cur.execute("""
        SELECT account_id, date_start, spend, action_values
        FROM raw.meta_customaccount_insights_daily
        WHERE action_values IS NOT NULL
        ORDER BY date_start DESC LIMIT 2
    """)
    for row in cur.fetchall():
        print(f"  acct={row[0]} date={row[1]} spend={row[2]}")
        print(f"    action_values={str(row[3])[:400]}")

    conn.close()


if __name__ == "__main__":
    main()
