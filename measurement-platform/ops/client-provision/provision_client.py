#!/usr/bin/env python3
"""
provision_client.py — Automated client provisioning for the measurement platform.

Generates client env file, runs schema migrations, creates Metabase dashboards,
and prints remaining manual steps (Airbyte, Slack bot, Prefect).

Usage:
  python provision_client.py acme
  python provision_client.py acme --supabase-url https://xxx.supabase.co --supabase-key eyJ...

PowerShell:
  cd "C:\\...\\measurement-platform\\ops\\client-provision"
  python provision_client.py acme --supabase-url "https://xxx.supabase.co" --supabase-key "eyJ..."
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def generate_env_file(client_slug: str, args: argparse.Namespace) -> Path:
    """Generate .env.{client_slug} from .env.example with provided values.

    Shared-DB model: all clients use the SAME Supabase project.
    The env file includes CLIENT_SLUG so each service knows which client's data to use.
    """
    template = REPO_ROOT / ".env.example"
    out = REPO_ROOT / f".env.{client_slug}"

    if out.exists():
        print(f"  .env.{client_slug} already exists — skipping generation")
        return out

    content = template.read_text() if template.exists() else ""

    replacements: dict[str, str] = {}
    if args.supabase_url:
        replacements["SUPABASE_URL="] = f"SUPABASE_URL={args.supabase_url}"
    if args.supabase_key:
        replacements["SUPABASE_SERVICE_KEY="] = f"SUPABASE_SERVICE_KEY={args.supabase_key}"
    if args.supabase_db_url:
        replacements["SUPABASE_DB_URL="] = f"SUPABASE_DB_URL={args.supabase_db_url}"
    if args.supabase_db_host:
        replacements["SUPABASE_DB_HOST="] = f"SUPABASE_DB_HOST={args.supabase_db_host}"
    if args.supabase_db_user:
        replacements["SUPABASE_DB_USER="] = f"SUPABASE_DB_USER={args.supabase_db_user}"
    if args.supabase_db_password:
        replacements["SUPABASE_DB_PASSWORD="] = f"SUPABASE_DB_PASSWORD={args.supabase_db_password}"
    if args.slack_channel_id:
        replacements["SLACK_ALERT_CHANNEL_ID="] = f"SLACK_ALERT_CHANNEL_ID={args.slack_channel_id}"

    lines = content.splitlines()
    new_lines = [f"# Client: {client_slug} (shared-DB multi-tenant)", f"CLIENT_SLUG={client_slug}"]
    for line in lines:
        replaced = False
        for prefix, replacement in replacements.items():
            if line.startswith(prefix):
                new_lines.append(replacement)
                replaced = True
                break
        if not replaced:
            new_lines.append(line)

    out.write_text("\n".join(new_lines) + "\n")
    print(f"  Generated {out.name} (CLIENT_SLUG={client_slug})")
    return out


def register_client(client_slug: str, args: argparse.Namespace) -> None:
    """Register client in client_config table (shared DB)."""
    db_url = args.supabase_db_url
    if not db_url:
        print(f"  No --supabase-db-url — register client manually:")
        print(f"    INSERT INTO client_config (client_slug) VALUES ('{client_slug}') ON CONFLICT DO NOTHING;")
        return

    psql = shutil.which("psql")
    if not psql:
        print(f"  psql not on PATH — register client manually in SQL Editor:")
        print(f"    INSERT INTO client_config (client_slug) VALUES ('{client_slug}') ON CONFLICT DO NOTHING;")
        return

    sql = f"INSERT INTO client_config (client_slug) VALUES ('{client_slug}') ON CONFLICT (client_slug) DO NOTHING;"
    result = subprocess.run(
        [psql, db_url, "-c", sql],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        print(f"  Registered client '{client_slug}' in client_config")
    else:
        print(f"  WARNING: {result.stderr[:200]}")


def run_schema_migrations(args: argparse.Namespace) -> None:
    """Run warehouse schema SQL files via psql if a DB URL is available.

    For the first client this creates all tables. For subsequent clients,
    the migrations are idempotent (IF NOT EXISTS / IF NOT) and only
    065_multi_tenant.sql needs to run once to add client_slug columns.
    """
    schema_dir = REPO_ROOT / "warehouse" / "schema"
    if not schema_dir.exists():
        print("  warehouse/schema/ not found — skipping")
        return

    db_url = args.supabase_db_url
    if not db_url:
        print("  No --supabase-db-url provided.")
        print("  Run these manually in Supabase SQL Editor:")
        for f in sorted(schema_dir.glob("*.sql")):
            print(f"    {f.name}")
        return

    psql = shutil.which("psql")
    if not psql:
        print("  psql not found on PATH — run migrations manually:")
        for f in sorted(schema_dir.glob("*.sql")):
            print(f"    psql \"{db_url}\" -f {f}")
        return

    for f in sorted(schema_dir.glob("*.sql")):
        print(f"  Running {f.name}...")
        result = subprocess.run(
            [psql, db_url, "-f", str(f)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"    WARNING: {f.name} had errors: {result.stderr[:200]}")
        else:
            print(f"    OK")


def create_dbt_profile(client_slug: str, args: argparse.Namespace) -> None:
    """Generate dbt profiles.yml for this client."""
    dbt_dir = REPO_ROOT / "dbt"
    template = dbt_dir / "profiles.yml.template"
    target = dbt_dir / "profiles.yml"

    if not template.exists():
        print("  profiles.yml.template not found — skipping")
        return

    if target.exists():
        print("  profiles.yml already exists — skipping (update manually if needed)")
        return

    shutil.copy(template, target)
    print(f"  Copied profiles.yml.template → profiles.yml")
    print(f"  Set SUPABASE_DB_* env vars from .env.{client_slug} before running dbt")


def create_dashboards(client_slug: str, args: argparse.Namespace) -> None:
    """Create Metabase dashboards for this client."""
    metabase_dir = REPO_ROOT / "dashboards" / "metabase"

    if not args.metabase_email or not args.metabase_password:
        print("  No --metabase-email/--metabase-password — skipping dashboard creation")
        print("  Run manually:")
        db_flag = f' --database-name "measurement-{client_slug}"' if not args.database_id else f" --database-id {args.database_id}"
        print(f'    python create_mvp_dashboards.py --client "{client_slug}"{db_flag}')
        print(f'    python create_kpi_number_cards.py --client "{client_slug}"{db_flag}')
        return

    env = os.environ.copy()
    env["METABASE_EMAIL"] = args.metabase_email
    env["METABASE_PASSWORD"] = args.metabase_password
    if args.metabase_url:
        env["METABASE_URL"] = args.metabase_url

    db_args = []
    if args.database_id:
        db_args = ["--database-id", str(args.database_id)]
    else:
        db_args = ["--database-name", f"measurement-{client_slug}"]

    for script in ["create_mvp_dashboards.py", "create_kpi_number_cards.py"]:
        script_path = metabase_dir / script
        if not script_path.exists():
            continue
        cmd = [sys.executable, str(script_path), "--client", client_slug] + db_args
        print(f"  Running {script}...")
        result = subprocess.run(cmd, cwd=str(metabase_dir), env=env, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"    WARNING: {result.stderr[:300]}")
        else:
            for line in result.stdout.strip().splitlines()[-5:]:
                print(f"    {line}")


def print_remaining_steps(client_slug: str) -> None:
    """Print manual steps that can't be automated."""
    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Remaining manual steps for '{client_slug}'
  Architecture: shared-DB (all clients in one Supabase)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  AIRBYTE (data ingestion — writes to raw_{client_slug} schema)
    1. Create Airbyte connections for {client_slug}
    2. Add sources: Meta Ads, Google Ads, TikTok Ads, Shopify, Klaviyo
    3. Set destination: shared Supabase, namespace = raw_{client_slug}
    4. Schedule daily sync; backfill 90 days
    See: ops/client-provision/INGESTION.md

  DBT (run with client_slug var)
    cd dbt
    dbt deps
    dbt run --vars '{{client_slug: {client_slug}, raw_schema: raw_{client_slug}}}'
    dbt test --vars '{{client_slug: {client_slug}, raw_schema: raw_{client_slug}}}'

  SLACK BOT (one bot per client — same shared DB)
    1. Create Slack channel: #measurement-{client_slug}
    2. Copy services/slack-bot/.env.example -> .env.{client_slug}
    3. Set CLIENT_SLUG={client_slug}
    4. Set SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET (client's Slack app)
    5. Set SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_DB_URL (shared DB)
    6. Set PORT to a unique port (3001, 3002, etc.)
    7. Deploy: npm install && npm run build && node dist/index.js

  PREFECT (per-client deployment — same shared DB)
    Set CLIENT_SLUG={client_slug} plus SUPABASE_* vars, then:
    CLIENT_SLUG={client_slug} bash orchestration/prefect/deployments/deploy.sh

  METABASE (dashboards use client_slug filter)
    Dashboards filter by {{{{client_slug}}}} — wire the "Client" filter
    to '{client_slug}' for this client's dashboard.
    If dashboards weren't auto-created above:
      python dashboards/metabase/create_mvp_dashboards.py --client {client_slug}
      python dashboards/metabase/create_kpi_number_cards.py --client {client_slug}

  Use ops/client-provision/onboarding_checklist.md to track progress.
""")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provision a new client for the measurement platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("client_slug", help="Client identifier (e.g. acme, beta)")

    g = parser.add_argument_group("Supabase")
    g.add_argument("--supabase-url", help="Supabase project URL")
    g.add_argument("--supabase-key", help="Supabase service role key")
    g.add_argument("--supabase-db-url", help="Supabase direct DB URL (postgresql://...)")
    g.add_argument("--supabase-db-host", help="Supabase DB host")
    g.add_argument("--supabase-db-user", help="Supabase DB user")
    g.add_argument("--supabase-db-password", help="Supabase DB password")

    g = parser.add_argument_group("Metabase")
    g.add_argument("--metabase-url", default="http://localhost:3000", help="Metabase URL")
    g.add_argument("--metabase-email", help="Metabase admin email")
    g.add_argument("--metabase-password", help="Metabase admin password")
    g.add_argument("--database-id", type=int, help="Metabase database id for this client")

    g = parser.add_argument_group("Slack")
    g.add_argument("--slack-channel-id", help="Slack alert channel ID for this client")

    args = parser.parse_args()
    slug = args.client_slug

    print(f"\n{'='*60}")
    print(f"  Provisioning client: {slug}")
    print(f"  Architecture: shared-DB (one Supabase for all clients)")
    print(f"{'='*60}\n")

    print("[1/6] Generating .env file...")
    generate_env_file(slug, args)

    print("\n[2/6] Running schema migrations (idempotent)...")
    run_schema_migrations(args)

    print("\n[3/6] Registering client in client_config...")
    register_client(slug, args)

    print("\n[4/6] Setting up dbt profile...")
    create_dbt_profile(slug, args)

    print("\n[5/6] Creating Metabase dashboards...")
    create_dashboards(slug, args)

    print("\n[6/6] Remaining manual steps...")
    print_remaining_steps(slug)

    return 0


if __name__ == "__main__":
    sys.exit(main())
