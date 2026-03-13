"""
run_experiments.py — Run queued experiments (GeoLift / CausalImpact) and write results to experiment_results.
Triggered by schedule or manually; reads experiments where status = 'queued'.
"""

import os
import subprocess
from pathlib import Path

from prefect import flow, task


@task
def fetch_queued_experiments() -> list:
    """Fetch experiments with status = 'queued' for this client from Supabase."""
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        slug = os.environ.get("CLIENT_SLUG", "default")
        if not url or not key:
            return []
        client = create_client(url, key)
        r = client.table("experiments").select("*").eq("client_slug", slug).eq("status", "queued").execute()
        return r.data or []
    except Exception as e:
        print(f"Fetch queued experiments failed: {e}")
        return []


@task
def run_model_runner(experiment: dict) -> bool:
    """Call model-runner (runner.py) for this experiment."""
    slug = experiment.get("experiment_slug")
    exp_type = experiment.get("experiment_type")
    start = experiment.get("start_date")
    end = experiment.get("end_date")
    config = experiment.get("config") or {}
    if not slug or not exp_type or not start or not end:
        return False

    runner_dir = Path(__file__).resolve().parents[2] / "services" / "model-runner" / "src"
    env = os.environ.copy()
    # Ensure Python path and Supabase env
    env.setdefault("PYTHONPATH", str(runner_dir))

    if exp_type == "geolift":
        treatment = ",".join(config.get("treatment_geos") or [])
        holdout = ",".join(config.get("holdout_geos") or [])
        result = subprocess.run(
            ["python", "-m", "runner", "geolift", slug, start, end, treatment, holdout],
            cwd=str(runner_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=3600,
        )
    elif exp_type == "causal_impact":
        intervention = config.get("intervention_date") or start
        metric = config.get("metric") or "revenue"
        result = subprocess.run(
            ["python", "-m", "runner", "causalimpact", slug, start, end, intervention, metric],
            cwd=str(runner_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=3600,
        )
    else:
        print(f"Unknown experiment_type: {exp_type}")
        return False

    if result.returncode != 0:
        print(result.stderr)
        return False
    return True


@flow(name="run_experiments", description="Run queued GeoLift / CausalImpact experiments")
def run_experiments() -> None:
    experiments = fetch_queued_experiments.submit().result()
    for exp in experiments:
        run_model_runner.submit(exp).result()
