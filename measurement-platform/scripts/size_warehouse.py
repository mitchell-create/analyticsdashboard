"""Size the Supabase warehouse: per-schema totals + top-N largest tables.

Reads SUPABASE_DB_URL from measurement-platform/.env.
Pure read-only queries against pg_catalog.
"""

import os
from pathlib import Path
import psycopg2
import psycopg2.extras


def load_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:>7.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"


def main() -> None:
    load_env()
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("ERROR: SUPABASE_DB_URL not set"); return

    conn = psycopg2.connect(db_url, connect_timeout=20)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT pg_database_size(current_database()) AS bytes")
    total = int(cur.fetchone()["bytes"])
    print(f"\n=== TOTAL DATABASE SIZE: {fmt_bytes(total)} ===\n")

    cur.execute("""
        SELECT schemaname,
               SUM(pg_total_relation_size(format('%I.%I', schemaname, tablename)::regclass))::bigint AS total_bytes,
               COUNT(*)::int AS table_count
        FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog','information_schema','pg_toast')
        GROUP BY schemaname
        ORDER BY total_bytes DESC
    """)
    print(f"{'SCHEMA':<25} {'SIZE':>15} {'TABLES':>8}")
    print("-" * 50)
    for r in cur.fetchall():
        print(f"{r['schemaname']:<25} {fmt_bytes(int(r['total_bytes'] or 0)):>15} {r['table_count']:>8}")

    print(f"\n=== TOP 25 LARGEST TABLES ===\n")
    cur.execute("""
        SELECT schemaname, tablename,
               pg_total_relation_size(format('%I.%I', schemaname, tablename)::regclass)::bigint AS total_bytes,
               pg_relation_size(format('%I.%I', schemaname, tablename)::regclass)::bigint AS data_bytes,
               pg_indexes_size(format('%I.%I', schemaname, tablename)::regclass)::bigint AS index_bytes
        FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog','information_schema','pg_toast')
        ORDER BY total_bytes DESC
        LIMIT 25
    """)
    print(f"{'SCHEMA.TABLE':<55} {'TOTAL':>12} {'DATA':>12} {'INDEX':>12}")
    print("-" * 95)
    for r in cur.fetchall():
        name = f"{r['schemaname']}.{r['tablename']}"
        print(f"{name:<55} {fmt_bytes(int(r['total_bytes'])):>12} {fmt_bytes(int(r['data_bytes'])):>12} {fmt_bytes(int(r['index_bytes'])):>12}")

    print(f"\n=== ROW COUNTS (top 15 by size) ===\n")
    cur.execute("""
        SELECT schemaname, tablename,
               pg_total_relation_size(format('%I.%I', schemaname, tablename)::regclass)::bigint AS sz
        FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog','information_schema','pg_toast')
        ORDER BY sz DESC LIMIT 15
    """)
    targets = cur.fetchall()
    print(f"{'SCHEMA.TABLE':<55} {'ROWS':>15}")
    print("-" * 72)
    for r in targets:
        try:
            cur.execute(f'SELECT COUNT(*) AS c FROM "{r["schemaname"]}"."{r["tablename"]}"')
            n = cur.fetchone()["c"]
            print(f'{r["schemaname"]}.{r["tablename"]:<45} {n:>15,}')
        except Exception as e:
            print(f'{r["schemaname"]}.{r["tablename"]:<45} {"(error)":>15}')

    conn.close()


if __name__ == "__main__":
    main()
