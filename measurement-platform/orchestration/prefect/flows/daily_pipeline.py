"""
daily_pipeline.py — Daily flow: Airbyte sync check → dbt run → dbt test → QA checks → Slack alerts on failure.
Run via Prefect deployment (e.g. daily schedule).
"""

import os
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

from prefect import flow, task
from prefect.logging import get_run_logger
from prefect.tasks import task_input_hash
from prefect.blocks.system import Secret

# Optional: use Prefect Slack block or env SLACK_BOT_TOKEN + SLACK_ALERT_CHANNEL_ID for alerts
def _post_slack_alert(message: str) -> None:
    try:
        from slack_sdk import WebClient
        token = os.environ.get("SLACK_BOT_TOKEN")
        channel = os.environ.get("SLACK_ALERT_CHANNEL_ID")
        if token and channel:
            client = WebClient(token=token)
            client.chat_postMessage(channel=channel, text=message)
    except Exception as e:
        print(f"Slack alert failed: {e}")


@task
def check_airbyte_sync() -> bool:
    """Check that Airbyte sync completed (e.g. call Airbyte API or check last sync timestamp)."""
    api_key = os.environ.get("AIRBYTE_API_KEY")
    workspace_id = os.environ.get("AIRBYTE_WORKSPACE_ID")
    if not api_key or not workspace_id:
        print("AIRBYTE_API_KEY or AIRBYTE_WORKSPACE_ID not set; skipping sync check")
        return True
    # Placeholder: call Airbyte API to list last syncs and verify success
    # requests.get(f"https://api.airbyte.com/v1/workspaces/{workspace_id}/connections", ...)
    return True


def _repo_dbt_dir() -> Path:
    """Repo root is 3 levels up from this file: flows -> prefect -> orchestration -> repo_root."""
    return Path(__file__).resolve().parents[3] / "dbt"


@task
def run_dbt() -> tuple[bool, str | None]:
    """Run dbt run (staging + marts). Returns (success, error_message)."""
    logger = get_run_logger()
    dbt_dir = os.environ.get("DBT_PROJECT_DIR", str(_repo_dbt_dir()))
    if not Path(dbt_dir).joinpath("dbt_project.yml").exists():
        logger.warning(f"dbt project not found at {dbt_dir}; skipping dbt run")
        return True, None
    try:
        result = subprocess.run(
            ["dbt", "run"],
            cwd=dbt_dir,
            capture_output=True,
            text=True,
            timeout=3600,
        )
    except FileNotFoundError as e:
        logger.error(f"dbt command not found: {e}")
        return False, f"dbt not found in PATH. Add Python Scripts to Path."
    except subprocess.TimeoutExpired:
        return False, "dbt run timed out after 3600s"
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Unknown error")[:500]  # truncate for DB
        logger.error(f"dbt run failed: {err}")
        return False, err
    return True, None


@task
def run_dbt_test() -> bool:
    """Run dbt test."""
    dbt_dir = os.environ.get("DBT_PROJECT_DIR", str(_repo_dbt_dir()))
    if not Path(dbt_dir).joinpath("dbt_project.yml").exists():
        return True
    result = subprocess.run(
        ["dbt", "test"],
        cwd=dbt_dir,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        print(result.stderr)
        return False
    return True


@task
def record_pipeline_run(status: str, flow_name: str, message: str = "") -> None:
    """Record run in pipeline_runs via direct Postgres."""
    logger = get_run_logger()
    try:
        from _db import execute
        now_utc = datetime.now(timezone.utc)
        ok = execute(
            """INSERT INTO public.pipeline_runs
                 (run_date, flow_name, status, started_at, finished_at, message)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (date.today(), flow_name, status, now_utc, now_utc, message or None),
        )
        if not ok:
            logger.warning("Record pipeline run SKIPPED: SUPABASE_DB_URL not set")
            return
        logger.info(f"Record pipeline run OK: status={status}")
    except Exception as e:
        logger.error(f"Record pipeline run failed: {e}")


@flow(name="daily_pipeline", description="Daily sync + dbt + QA")
def daily_pipeline() -> None:
    flow_name = "daily_pipeline"
    run_date = date.today().isoformat()

    # Record start so we can see runs in pipeline_runs even if flow fails early
    record_pipeline_run.submit("running", flow_name, "Pipeline started").result()

    ok = check_airbyte_sync.submit().result()
    if not ok:
        record_pipeline_run.submit("failed", flow_name, "Airbyte sync check failed").result()
        _post_slack_alert(f":x: *Daily pipeline failed*\nDate: {run_date}\nStep: Airbyte sync check failed")
        return

    ok, dbt_err = run_dbt.submit().result()
    if not ok:
        msg = f"dbt run failed: {dbt_err}" if dbt_err else "dbt run failed"
        record_pipeline_run.submit("failed", flow_name, msg).result()
        _post_slack_alert(f":x: *Daily pipeline failed*\nDate: {run_date}\nStep: {msg}")
        return

    ok = run_dbt_test.submit().result()
    if not ok:
        record_pipeline_run.submit("failed", flow_name, "dbt test failed").result()
        _post_slack_alert(f":x: *Daily pipeline failed*\nDate: {run_date}\nStep: dbt test failed")
        return

    # QA checks: run qa_checks flow if deployed, or schedule separately
    # prefect deployment run qa_checks/qa_checks

    record_pipeline_run.submit("success", flow_name).result()


if __name__ == "__main__":
    daily_pipeline()
