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
    """Generate .env.{client_slug} from .env.example with provided values."""
    template = REPO_ROOT / ".env.example"
    out = REPO_ROOT / f".env.{client_slug}"

    if out.exists():
        print(f"  .env.{client_slug} already exists — skipping generation")
        return out

    content = template.read_text() if template.exists() else ""

    replacements = {}
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
    new_lines = []
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
    print(f"  Generated {out.name}")
    return out


def run_schema_migrations(args: argparse.Namespace) -> None:
    """Run warehouse schema SQL files via psql if a DB URL is available."""
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
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  AIRBYTE (data ingestion)
    1. Create Airbyte workspace for {client_slug}
    2. Add sources: Meta Ads, Google Ads, TikTok Ads, Shopify, Klaviyo
    3. Set destination: this client's Supabase (connection string)
    4. Schedule daily sync; backfill 90 days
    See: ops/client-provision/INGESTION.md

  DBT (after Airbyte sync completes)
    1. Source .env.{client_slug} (or set SUPABASE_DB_* env vars)
    2. cd dbt && dbt deps && dbt seed && dbt run && dbt test

  SLACK BOT (one bot per client)
    1. Create Slack channel: #measurement-{client_slug}
    2. Copy services/slack-bot/.env.example → .env.{client_slug}
    3. Set SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET for this client's Slack app
    4. Set SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_DB_URL for this client
    5. Deploy: cd services/slack-bot && npm install && npm run build
    6. Start: node dist/index.js  (use PM2 or systemd for production)
    Note: Each client gets its OWN bot process with its own .env.

  PREFECT (orchestration)
    1. Set env vars for this client in a dedicated terminal/process
    2. Deploy:
       prefect deployment build orchestration/prefect/flows/daily_pipeline.py:daily_pipeline \\
         --name "{client_slug}-daily" --cron "0 6 * * *"
       prefect deployment apply daily_pipeline-deployment.yaml
    3. Start worker: prefect worker start --pool default-pool

  METABASE (if dashboards weren't auto-created above)
    1. Add this client's Supabase as a database in Metabase
       Name it: measurement-{client_slug}
    2. Run:
       python dashboards/metabase/create_mvp_dashboards.py --client {client_slug} --database-name "measurement-{client_slug}"
       python dashboards/metabase/create_kpi_number_cards.py --client {client_slug} --database-name "measurement-{client_slug}"
    3. Wire date filters to all cards (see KPI_NUMBER_CARDS_SETUP.md)

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
    print(f"{'='*60}\n")

    print("[1/5] Generating .env file...")
    generate_env_file(slug, args)

    print("\n[2/5] Running schema migrations...")
    run_schema_migrations(args)

    print("\n[3/5] Setting up dbt profile...")
    create_dbt_profile(slug, args)

    print("\n[4/5] Creating Metabase dashboards...")
    create_dashboards(slug, args)

    print("\n[5/5] Remaining manual steps...")
    print_remaining_steps(slug)

    return 0


if __name__ == "__main__":
    sys.exit(main())
