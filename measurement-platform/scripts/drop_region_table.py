"""Drop raw.meta_ads_insights_region from Supabase. Safe — verifies size before drop."""

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

    cur.execute("""
        SELECT pg_size_pretty(pg_total_relation_size('raw.meta_ads_insights_region')),
               (SELECT COUNT(*) FROM raw.meta_ads_insights_region)
    """)
    size, rows = cur.fetchone()
    print(f"Before drop: {size}, {rows:,} rows")

    cur.execute("DROP TABLE IF EXISTS raw.meta_ads_insights_region CASCADE")
    conn.commit()
    print("DROP TABLE executed.")

    cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
    new_total = cur.fetchone()[0]
    print(f"Database size after drop: {new_total}")

    conn.close()


if __name__ == "__main__":
    main()
