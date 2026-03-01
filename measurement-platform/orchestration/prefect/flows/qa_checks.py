"""
qa_checks.py — QA anomaly checks: missing dates, spend/revenue anomalies; post to data_quality_flags and Slack.
"""

import os
from datetime import date, timedelta

from prefect import flow, task


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


def _get_supabase():
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def _insert_quality_flag(client, check_name: str, severity: str, message: str) -> None:
    client.table("data_quality_flags").insert({
        "flag_date": date.today().isoformat(),
        "check_name": check_name,
        "severity": severity,
        "message": message,
    }).execute()


@task
def check_missing_revenue_dates() -> bool:
    """Flag if fact_kpi_daily has no row for yesterday (or last 3 days)."""
    client = _get_supabase()
    if not client:
        return True
    # Use marts schema if dbt writes there
    try:
        r = client.table("fact_kpi_daily").select("report_date").gte(
            "report_date", (date.today() - timedelta(days=7)).isoformat()
        ).order("report_date", desc=True).limit(7).execute()
        dates = {row["report_date"] for row in (r.data or [])}
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        if yesterday not in dates:
            _insert_quality_flag(client, "missing_revenue_date", "warning", f"No fact_kpi_daily row for {yesterday}")
            _post_slack_alert(f":warning: *QA*\nMissing revenue date: {yesterday}")
        return True
    except Exception as e:
        print(e)
        return False


@task
def check_spend_anomaly() -> bool:
    """Flag if total spend yesterday is >2x or <0.5x 7-day average (simple heuristic)."""
    client = _get_supabase()
    if not client:
        return True
    try:
        r = client.table("fact_spend_daily").select("report_date,spend").gte(
            "report_date", (date.today() - timedelta(days=14)).isoformat()
        ).execute()
        data = r.data or []
        by_date = {}
        for row in data:
            d = row["report_date"]
            by_date[d] = by_date.get(d, 0) + float(row.get("spend") or 0)
        if len(by_date) < 7:
            return True
        recent = sorted(by_date.keys(), reverse=True)[:7]
        avg = sum(by_date[d] for d in recent) / 7
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        if yesterday not in by_date:
            return True
        spend_yesterday = by_date[yesterday]
        if avg > 0 and (spend_yesterday > 2 * avg or spend_yesterday < 0.5 * avg):
            _insert_quality_flag(
                client, "spend_anomaly", "warning",
                f"Spend {yesterday}: {spend_yesterday:.0f} vs 7d avg {avg:.0f}"
            )
            _post_slack_alert(f":warning: *QA*\nSpend anomaly on {yesterday}: {spend_yesterday:.0f} vs 7d avg {avg:.0f}")
        return True
    except Exception as e:
        print(e)
        return False


@flow(name="qa_checks", description="Data quality checks and Slack alerts")
def qa_checks() -> None:
    check_missing_revenue_dates.submit().result()
    check_spend_anomaly.submit().result()
