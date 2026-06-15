"""
data_sync.py — Bi-monthly direct-API data sync + dbt build.

Runs the direct sync scripts (Meta, Klaviyo, GA4) against the platform APIs,
then dbt run + test, so the warehouse is fresh before the scheduled client
reports fire (14th / 1st). Replaces the old Airbyte-based
start-airbyte-sync.ps1 pipeline.

Schedule (see prefect.yaml):
  - 2am ET on the 13th  -> feeds the 14th "last 14 days" report
  - 2am ET on the 1st   -> feeds the 1st "previous full month" report

Each sync script self-loads measurement-platform/.env, and this flow also
loads it so Slack alerting + pipeline_runs logging have their credentials
regardless of the worker's environment.

A failing source does NOT abort the others; dbt still runs as long as at least
one source synced. The Slack summary reports per-source status.
"""

import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from shutil import which

from prefect import flow, task
from prefect.logging import get_run_logger


REPORTING_LOOKBACK_DAYS = 45


# ─── Paths ────────────────────────────────────────────────────────────────────

def _orchestration_dir() -> Path:
    # flows -> prefect -> orchestration
    return Path(__file__).resolve().parents[2]


def _measurement_platform_dir() -> Path:
    # flows -> prefect -> orchestration -> measurement-platform
    return Path(__file__).resolve().parents[3]


def load_env() -> None:
    """Load measurement-platform/.env so this flow has DB/Slack/API creds."""
    env_path = _measurement_platform_dir() / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _post_slack(message: str) -> None:
    try:
        from slack_sdk import WebClient
        token = os.environ.get("SLACK_BOT_TOKEN")
        channel = os.environ.get("SLACK_ALERT_CHANNEL_ID")
        if token and channel:
            WebClient(token=token).chat_postMessage(channel=channel, text=message)
    except Exception as e:
        print(f"Slack post failed: {e}")


def _record_run(status: str, message: str = "") -> None:
    """Best-effort write to public.pipeline_runs (never aborts the flow)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from _db import execute
        now_utc = datetime.now(timezone.utc)
        execute(
            """INSERT INTO public.pipeline_runs
                 (run_date, flow_name, status, started_at, finished_at, message)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (date.today(), "data_sync", status, now_utc,
             None if status == "running" else now_utc, message[:1000] or None),
        )
    except Exception as e:
        print(f"pipeline_runs insert failed: {e}")


def _run_script(script_name: str, args: list[str] | None = None,
                timeout: int = 1800) -> tuple[bool, str]:
    """Run a sync script via subprocess. Returns (success, short detail)."""
    logger = get_run_logger()
    script = _orchestration_dir() / script_name
    if not script.exists():
        return False, f"{script_name} not found"
    try:
        result = subprocess.run(
            [sys.executable, str(script)] + (args or []),
            cwd=str(_orchestration_dir()),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    if result.returncode != 0:
        tail = ((result.stderr or "") + (result.stdout or "")).strip()[-300:]
        logger.error(f"{script_name} failed: {tail}")
        return False, tail or f"exit {result.returncode}"
    # Pull the last non-empty line as a one-line summary (scripts print a DONE line)
    last = next((ln for ln in reversed((result.stdout or "").splitlines()) if ln.strip()), "ok")
    logger.info(f"{script_name} OK: {last.strip()}")
    return True, last.strip()[:200]


# ─── Tasks ────────────────────────────────────────────────────────────────────

@task
def sync_meta() -> tuple[bool, str]:
    return _run_script("meta_sync.py")


@task
def sync_meta_creative() -> tuple[bool, str]:
    """Ad-level (creative) Meta insights — feeds creative analysis (playbook §4.3)."""
    start_date = (date.today() - timedelta(days=REPORTING_LOOKBACK_DAYS)).isoformat()
    return _run_script("meta_creative_sync.py", ["--start-date", start_date])


@task
def sync_klaviyo() -> tuple[bool, str]:
    start_date = (date.today() - timedelta(days=REPORTING_LOOKBACK_DAYS)).isoformat()
    return _run_script("klaviyo_sync.py", ["--start-date", start_date])


@task
def sync_ga4() -> tuple[bool, str]:
    start_date = (date.today() - timedelta(days=REPORTING_LOOKBACK_DAYS)).isoformat()
    return _run_script("ga4_sync.py", ["--start-date", start_date])


@task
def sync_google() -> tuple[bool, str]:
    start_date = (date.today() - timedelta(days=REPORTING_LOOKBACK_DAYS)).isoformat()
    return _run_script("google_ads_sync.py", ["--start-date", start_date])


@task
def run_dbt() -> tuple[bool, str]:
    """dbt run + dbt test from the dbt project dir."""
    logger = get_run_logger()
    dbt_dir = os.environ.get("DBT_PROJECT_DIR", str(_measurement_platform_dir() / "dbt"))
    if not Path(dbt_dir, "dbt_project.yml").exists():
        return False, f"dbt project not found at {dbt_dir}"
    dbt_exe = which("dbt")
    dbt_cmd = [dbt_exe] if dbt_exe else [sys.executable, "-m", "dbt.cli.main"]
    try:
        # Refresh seeds first so client_ad_accounts stays in sync with the CSV
        # (new accounts/clients won't reach the marts otherwise).
        subprocess.run(dbt_cmd + ["seed"], cwd=dbt_dir,
                       capture_output=True, text=True, timeout=600)
        run = subprocess.run(dbt_cmd + ["run"], cwd=dbt_dir,
                             capture_output=True, text=True, timeout=3600)
        if run.returncode != 0:
            err = (run.stderr or run.stdout or "")[-300:]
            logger.error(f"dbt run failed: {err}")
            return False, f"dbt run failed: {err}"
        test = subprocess.run(dbt_cmd + ["test"], cwd=dbt_dir,
                              capture_output=True, text=True, timeout=1200)
    except subprocess.TimeoutExpired:
        return False, "dbt timed out"
    except FileNotFoundError:
        return False, "dbt not found on PATH"
    # dbt test failures are data-quality warnings, not a hard sync failure
    test_note = "tests pass" if test.returncode == 0 else "tests had failures"
    return True, f"dbt run ok, {test_note}"


# ─── Flow ─────────────────────────────────────────────────────────────────────

@flow(name="data_sync",
      description="Bi-monthly direct-API sync (Meta/Google/Klaviyo/GA4) + dbt build")
def data_sync() -> None:
    logger = get_run_logger()
    load_env()
    run_date = date.today().isoformat()
    logger.info(f"data_sync starting {run_date}")
    _record_run("running", "sync started")

    results: dict[str, tuple[bool, str]] = {}
    results["meta"] = sync_meta.submit().result()
    results["meta_creative"] = sync_meta_creative.submit().result()
    results["google"] = sync_google.submit().result()
    results["klaviyo"] = sync_klaviyo.submit().result()
    results["ga4"] = sync_ga4.submit().result()

    # Only rebuild dbt if at least one source refreshed (else marts are unchanged)
    if any(ok for ok, _ in results.values()):
        results["dbt"] = run_dbt.submit().result()
    else:
        results["dbt"] = (False, "skipped - all syncs failed")

    lines = [f":arrows_counterclockwise: *Data Sync* - {run_date}"]
    for name, (ok, detail) in results.items():
        icon = ":white_check_mark:" if ok else ":x:"
        lines.append(f"{icon} *{name}*: {detail}")
    summary = "\n".join(lines)

    all_ok = all(ok for ok, _ in results.values())
    status = "success" if all_ok else "partial_failure"
    _record_run(status, summary)
    _post_slack(summary)
    logger.info(f"data_sync done: {status}")


if __name__ == "__main__":
    data_sync()
