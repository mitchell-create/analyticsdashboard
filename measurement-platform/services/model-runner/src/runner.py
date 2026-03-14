"""
runner.py — Orchestrates GeoLift and CausalImpact runs; reads from Supabase marts, writes experiment_results.
Usage:
  python runner.py geolift <experiment_slug> <start_date> <end_date> <treatment_geos> <holdout_geos>
  python runner.py causalimpact <experiment_slug> <start_date> <end_date> <intervention_date> [metric]
"""

import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

# Add src to path when run from service root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import (
    get_supabase,
    fetch_kpi_geo_daily,
    fetch_kpi_daily,
    fetch_tiktok_organic_daily,
    insert_experiment,
    upsert_experiment_results,
    update_experiment_status,
)


def _fill_missing_dates(
    data: List[dict],
    start_date: str,
    end_date: str,
    fieldnames: List[str],
) -> List[dict]:
    """Fill missing dates with zeros so CausalImpact gets a complete daily time series."""
    date_to_row = {}
    for r in data:
        d = r.get("report_date")
        if d is not None:
            d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            date_to_row[d_str] = dict(r)
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    filled = []
    current = start
    metric_cols = [c for c in fieldnames if c != "report_date"]
    while current <= end:
        d_str = current.strftime("%Y-%m-%d")
        if d_str in date_to_row:
            filled.append(date_to_row[d_str])
        else:
            row = {"report_date": d_str}
            for col in metric_cols:
                row[col] = 0
            filled.append(row)
        current += timedelta(days=1)
    return filled


def run_geolift(experiment_slug: str, start_date: str, end_date: str, treatment_geos: str, holdout_geos: str, treatment_start_date: str | None = None) -> None:
    supabase = get_supabase()
    if not supabase:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")

    # Create experiment row
    row = insert_experiment(
        supabase, experiment_slug, "geolift", start_date, end_date,
        config={
            "treatment_geos": treatment_geos.split(","),
            "holdout_geos": holdout_geos.split(","),
            **({"treatment_start_date": treatment_start_date} if treatment_start_date else {}),
        },
        status="running",
    )
    if not row:
        raise RuntimeError("Failed to insert experiment")
    experiment_id = row["id"]

    try:
        # Export fact_kpi_geo_daily to CSV for R
        data = fetch_kpi_geo_daily(supabase, start_date, end_date)
        data_path = Path(__file__).parent / f"geolift_input_{experiment_slug}.csv"
        if data:
            with open(data_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["report_date", "geo_id", "revenue", "orders"])
                w.writeheader()
                w.writerows(data)
        os.environ["GEOLIFT_DATA_CSV"] = str(data_path)

        # Run R script
        r_script = Path(__file__).parent / "geolift_runner.R"
        r_args = ["Rscript", str(r_script), experiment_slug, start_date, end_date, treatment_geos, holdout_geos]
        if treatment_start_date:
            r_args.append(treatment_start_date)
        subprocess.run(r_args, check=True, cwd=str(Path(__file__).parent))

        # Read results CSV and upsert
        results_path = Path(__file__).parent / f"geolift_results_{experiment_slug}.csv"
        if results_path.exists():
            with open(results_path) as f:
                r = csv.DictReader(f)
                results = [
                    {
                        "result_date": row["result_date"],
                        "metric": row.get("metric", "revenue"),
                        "value": float(row["value"]) if row.get("value") else None,
                        "interval_lower": float(row["interval_lower"]) if row.get("interval_lower") else None,
                        "interval_upper": float(row["interval_upper"]) if row.get("interval_upper") else None,
                        "metadata": row.get("metadata"),
                    }
                    for row in r
                ]
            upsert_experiment_results(supabase, experiment_id, results)
        update_experiment_status(supabase, experiment_id, "completed")
    except Exception as e:
        update_experiment_status(supabase, experiment_id, "failed")
        raise e


def run_causalimpact(
    experiment_slug: str, start_date: str, end_date: str, intervention_date: str, metric: str = "revenue"
) -> None:
    supabase = get_supabase()
    if not supabase:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")

    row = insert_experiment(
        supabase, experiment_slug, "causal_impact", start_date, end_date,
        config={"intervention_date": intervention_date, "metric": metric},
        status="running",
    )
    if not row:
        raise RuntimeError("Failed to insert experiment")
    experiment_id = row["id"]

    try:
        # Export daily series: for revenue/orders use fact_kpi_daily; for views use fact_tiktok_organic_daily
        data_path = Path(__file__).parent / f"causalimpact_input_{experiment_slug}.csv"
        if metric in ("revenue", "orders"):
            data = fetch_kpi_daily(supabase, start_date, end_date)
            fieldnames = ["report_date", "revenue", "orders"]
        else:
            data = fetch_tiktok_organic_daily(supabase, start_date, end_date)
            fieldnames = ["report_date", "views", "likes", "comments", "shares", "followers"]
        # Fill missing dates with zeros so CausalImpact gets a complete daily time series
        data = _fill_missing_dates(data, start_date, end_date, fieldnames)
        with open(data_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(data)
        os.environ["CAUSALIMPACT_DATA_CSV"] = str(data_path)

        r_script = Path(__file__).parent / "causalimpact_runner.R"
        subprocess.run(
            ["Rscript", str(r_script), experiment_slug, start_date, end_date, intervention_date, metric],
            check=True,
            cwd=str(Path(__file__).parent),
        )

        results_path = Path(__file__).parent / f"causalimpact_results_{experiment_slug}.csv"
        if results_path.exists():
            with open(results_path) as f:
                r = csv.DictReader(f)
                results = [
                    {
                        "result_date": row["result_date"],
                        "metric": row.get("metric", metric),
                        "value": float(row["value"]) if row.get("value") else None,
                        "interval_lower": float(row["interval_lower"]) if row.get("interval_lower") else None,
                        "interval_upper": float(row["interval_upper"]) if row.get("interval_upper") else None,
                        "metadata": row.get("metadata"),
                    }
                    for row in r
                ]
            upsert_experiment_results(supabase, experiment_id, results)
        update_experiment_status(supabase, experiment_id, "completed")
    except Exception as e:
        update_experiment_status(supabase, experiment_id, "failed")
        raise


def run_geolift_compute(
    experiment_slug: str, start_date: str, end_date: str,
    treatment_geos: str, holdout_geos: str, treatment_start_date: str | None = None,
) -> None:
    """Compute-only mode: export data via psycopg2, run R, output results CSV.
    Does NOT touch Supabase REST API (no experiment insert/status/results writes).
    The caller (Slack bot) handles all DB operations via Node.js."""
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL required for compute-only mode")

    import psycopg2
    from psycopg2.extras import RealDictCursor

    # Fetch geo KPI data directly via psycopg2
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT report_date, geo_id, revenue, orders
                   FROM public_marts.fact_kpi_geo_daily
                   WHERE report_date >= %s AND report_date <= %s
                   ORDER BY report_date""",
                (start_date, end_date),
            )
            data = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    if not data:
        raise RuntimeError(f"No data found for {start_date} to {end_date}")

    # Export to CSV for R
    data_path = Path(__file__).parent / f"geolift_input_{experiment_slug}.csv"
    with open(data_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["report_date", "geo_id", "revenue", "orders"])
        w.writeheader()
        for row in data:
            row["report_date"] = row["report_date"].strftime("%Y-%m-%d") if hasattr(row["report_date"], "strftime") else str(row["report_date"])[:10]
            w.writerow(row)
    os.environ["GEOLIFT_DATA_CSV"] = str(data_path)

    print(f"Exported {len(data)} rows to {data_path}")

    # Ensure experiment row exists (upsert via psycopg2)
    # The Slack bot flow creates this row first, but standalone runs may not have it.
    # Unique constraint is on (client_slug, experiment_slug).
    client_slug = os.environ.get("CLIENT_SLUG", "default")
    config_json = json.dumps({
        "treatment_geos": treatment_geos.split(","),
        "holdout_geos": holdout_geos.split(","),
        **({"treatment_start_date": treatment_start_date} if treatment_start_date else {}),
    })
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO public.experiments
                   (experiment_slug, experiment_type, start_date, end_date, config, status, client_slug)
                   VALUES (%s, 'geolift', %s, %s, %s, 'running', %s)
                   ON CONFLICT (client_slug, experiment_slug)
                   DO UPDATE SET status = 'running', updated_at = NOW()
                   RETURNING id""",
                (experiment_slug, start_date, end_date, config_json, client_slug),
            )
            experiment_id = cur.fetchone()[0]
        conn.commit()
        print(f"Experiment row ready: id={experiment_id}, client_slug={client_slug}")
    finally:
        conn.close()

    # Run R script
    r_script = Path(__file__).parent / "geolift_runner.R"
    r_args = ["Rscript", str(r_script), experiment_slug, start_date, end_date, treatment_geos, holdout_geos]
    if treatment_start_date:
        r_args.append(treatment_start_date)
    subprocess.run(r_args, check=True, cwd=str(Path(__file__).parent))

    # Read and print results so the caller can parse them
    results_path = Path(__file__).parent / f"geolift_results_{experiment_slug}.csv"
    if results_path.exists():
        with open(results_path) as f:
            reader = csv.DictReader(f)
            results = list(reader)
        print(f"RESULTS_COUNT={len(results)}")

        # Write results to DB via psycopg2 (bypass Supabase REST)
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                for row in results:
                    cur.execute(
                        """INSERT INTO public.experiment_results
                           (experiment_id, result_date, metric, value, interval_lower, interval_upper, metadata)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (experiment_id, result_date, metric)
                           DO UPDATE SET value = EXCLUDED.value,
                                         interval_lower = EXCLUDED.interval_lower,
                                         interval_upper = EXCLUDED.interval_upper,
                                         metadata = EXCLUDED.metadata""",
                        (
                            experiment_id,
                            row["result_date"],
                            row.get("metric", "revenue"),
                            float(row["value"]) if row.get("value") else None,
                            float(row["interval_lower"]) if row.get("interval_lower") else None,
                            float(row["interval_upper"]) if row.get("interval_upper") else None,
                            # metadata column is JSONB — wrap plain text in JSON object
                            json.dumps({"raw": row.get("metadata", "")}) if row.get("metadata") else None,
                        ),
                    )
                # Update experiment status
                cur.execute(
                    """UPDATE public.experiments SET status = 'completed', updated_at = NOW()
                       WHERE id = %s""",
                    (experiment_id,),
                )
            conn.commit()
            print(f"Wrote {len(results)} results to experiment_results via psycopg2")
        finally:
            conn.close()
    else:
        # Mark as failed
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE public.experiments SET status = 'failed', updated_at = NOW()
                       WHERE id = %s""",
                    (experiment_id,),
                )
            conn.commit()
        finally:
            conn.close()
        raise RuntimeError("R script did not produce results file")

    # Cleanup temp CSV files
    try:
        data_path.unlink()
    except OSError:
        pass
    try:
        results_path.unlink()
    except OSError:
        pass

    print(f"Done: {experiment_slug}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: runner.py geolift <slug> <start> <end> <treatment_geos> <holdout_geos> [treatment_start]")
        print("       runner.py geolift-compute <slug> <start> <end> <treatment> <holdout> [treatment_start]")
        print("       runner.py causalimpact <slug> <start> <end> <intervention_date> [metric]")
        sys.exit(1)
    cmd = sys.argv[1].lower()
    if cmd == "geolift":
        if len(sys.argv) < 7:
            print("Usage: runner.py geolift <slug> <start> <end> <treatment_geos> <holdout_geos> [treatment_start_date]")
            sys.exit(1)
        treatment_start = sys.argv[7] if len(sys.argv) > 7 else None
        run_geolift(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], treatment_start)
    elif cmd == "geolift-compute":
        if len(sys.argv) < 7:
            print("Usage: runner.py geolift-compute <slug> <start> <end> <treatment> <holdout> [treatment_start]")
            sys.exit(1)
        treatment_start = sys.argv[7] if len(sys.argv) > 7 else None
        run_geolift_compute(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], treatment_start)
    elif cmd == "causalimpact":
        if len(sys.argv) < 6:
            print("Usage: runner.py causalimpact <slug> <start> <end> <intervention_date> [metric]")
            sys.exit(1)
        metric = sys.argv[6] if len(sys.argv) > 6 else "revenue"
        run_causalimpact(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], metric)
    else:
        print("Unknown command:", cmd)
        sys.exit(1)


if __name__ == "__main__":
    main()
