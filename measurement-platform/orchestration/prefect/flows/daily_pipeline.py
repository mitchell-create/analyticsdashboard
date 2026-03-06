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


def _dbt_cmd(base_cmd: str) -> list[str]:
    """
    Build dbt command with optional client_slug vars.

    CLIENT_SLUG enables tenant-specific dbt model selection in shared-DB setups.
    """
    cmd = ["dbt", base_cmd]
    client_slug = os.environ.get("CLIENT_SLUG", "").strip()
    if client_slug:
        cmd.extend(["--vars", f"{{client_slug: {client_slug}}}"])
    return cmd


@task
def run_dbt() -> tuple[bool, str | None]:
    """Run dbt run (staging + marts). Returns (success, error_message)."""
    logger = get_run_logger()
    dbt_dir = os.environ.get("DBT_PROJECT_DIR", str(_repo_dbt_dir()))
    if not Path(dbt_dir).joinpath("dbt_project.yml").exists():
        logger.warning(f"dbt project not found at {dbt_dir}; skipping dbt run")
        return True, None
    try:
        command = _dbt_cmd("run")
        logger.info(f"Running command: {' '.join(command)}")
        result = subprocess.run(
            command,
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
    logger = get_run_logger()
    dbt_dir = os.environ.get("DBT_PROJECT_DIR", str(_repo_dbt_dir()))
    if not Path(dbt_dir).joinpath("dbt_project.yml").exists():
        return True
    command = _dbt_cmd("test")
    logger.info(f"Running command: {' '.join(command)}")
    result = subprocess.run(
        command,
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
    """Record run in pipeline_runs (Supabase)."""
    logger = get_run_logger()
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            logger.warning(f"Record pipeline run SKIPPED: SUPABASE_URL or SUPABASE_SERVICE_KEY not set (url={bool(url)}, key={bool(key)})")
            return
        client = create_client(url, key)
        client.table("pipeline_runs").insert({
            "run_date": date.today().isoformat(),
            "flow_name": flow_name,
            "status": status,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "message": message or None,
        }).execute()
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
        raise RuntimeError("Airbyte sync check failed")

    ok, dbt_err = run_dbt.submit().result()
    if not ok:
        msg = f"dbt run failed: {dbt_err}" if dbt_err else "dbt run failed"
        record_pipeline_run.submit("failed", flow_name, msg).result()
        _post_slack_alert(f":x: *Daily pipeline failed*\nDate: {run_date}\nStep: {msg}")
        raise RuntimeError(msg)

    ok = run_dbt_test.submit().result()
    if not ok:
        record_pipeline_run.submit("failed", flow_name, "dbt test failed").result()
        _post_slack_alert(f":x: *Daily pipeline failed*\nDate: {run_date}\nStep: dbt test failed")
        raise RuntimeError("dbt test failed")

    # QA checks: run qa_checks flow if deployed, or schedule separately
    # prefect deployment run qa_checks/qa_checks

    record_pipeline_run.submit("success", flow_name).result()


if __name__ == "__main__":
    daily_pipeline()
