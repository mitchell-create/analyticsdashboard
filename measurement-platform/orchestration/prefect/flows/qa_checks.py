"""
qa_checks.py — QA anomaly checks: missing dates, spend/revenue anomalies; post to data_quality_flags and Slack.
"""

import os
from datetime import date, timedelta

from prefect import flow, task

from _db import query, execute


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


def _insert_quality_flag(check_name: str, severity: str, message: str) -> None:
    try:
        execute(
            """INSERT INTO public.data_quality_flags
                 (flag_date, check_name, severity, message)
               VALUES (%s, %s, %s, %s)""",
            (date.today(), check_name, severity, message),
        )
    except Exception as e:
        print(f"Insert quality flag failed: {e}")


@task
def check_missing_revenue_dates() -> bool:
    """Flag if fact_kpi_daily has no row for yesterday."""
    try:
        rows = query(
            """SELECT DISTINCT report_date
               FROM public_marts.fact_kpi_daily
               WHERE report_date >= %s
               ORDER BY report_date DESC
               LIMIT 7""",
            (date.today() - timedelta(days=7),),
        )
        dates = {r["report_date"] for r in rows}
        yesterday = date.today() - timedelta(days=1)
        if yesterday not in dates:
            _insert_quality_flag(
                "missing_revenue_date",
                "warning",
                f"No fact_kpi_daily row for {yesterday.isoformat()}",
            )
            _post_slack_alert(f":warning: *QA*\nMissing revenue date: {yesterday.isoformat()}")
        return True
    except Exception as e:
        print(e)
        return False


@task
def check_spend_anomaly() -> bool:
    """Flag if total spend yesterday is >2x or <0.5x 7-day average (simple heuristic)."""
    try:
        rows = query(
            """SELECT report_date, SUM(spend)::numeric AS spend
               FROM public_marts.fact_spend_daily
               WHERE report_date >= %s
               GROUP BY report_date""",
            (date.today() - timedelta(days=14),),
        )
        if len(rows) < 7:
            return True
        by_date = {r["report_date"]: float(r["spend"] or 0) for r in rows}
        recent = sorted(by_date.keys(), reverse=True)[:7]
        avg = sum(by_date[d] for d in recent) / 7
        yesterday = date.today() - timedelta(days=1)
        if yesterday not in by_date:
            return True
        spend_yesterday = by_date[yesterday]
        if avg > 0 and (spend_yesterday > 2 * avg or spend_yesterday < 0.5 * avg):
            _insert_quality_flag(
                "spend_anomaly",
                "warning",
                f"Spend {yesterday.isoformat()}: {spend_yesterday:.0f} vs 7d avg {avg:.0f}",
            )
            _post_slack_alert(
                f":warning: *QA*\nSpend anomaly on {yesterday.isoformat()}: "
                f"{spend_yesterday:.0f} vs 7d avg {avg:.0f}"
            )
        return True
    except Exception as e:
        print(e)
        return False


@flow(name="qa_checks", description="Data quality checks and Slack alerts")
def qa_checks() -> None:
    check_missing_revenue_dates.submit().result()
    check_spend_anomaly.submit().result()
