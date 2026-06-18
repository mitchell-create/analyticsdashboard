from datetime import date
from types import SimpleNamespace

import scheduled_reports


def test_rest_query_returns_none_on_transport_failure(monkeypatch):
    monkeypatch.setattr(scheduled_reports, "SUPABASE_KEY", "service-key")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=22, stdout="", stderr="401 Unauthorized")

    monkeypatch.setattr(scheduled_reports.subprocess, "run", fake_run)

    assert scheduled_reports._rest_query("fact_spend_daily", "select=spend") is None


def test_rest_query_requires_list_payload(monkeypatch):
    monkeypatch.setattr(scheduled_reports, "SUPABASE_KEY", "service-key")

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout='{"message":"error"}', stderr="")

    monkeypatch.setattr(scheduled_reports.subprocess, "run", fake_run)

    assert scheduled_reports._rest_query("fact_spend_daily", "select=spend") is None


def test_fetch_via_rest_fails_closed_when_required_query_fails(monkeypatch):
    monkeypatch.setattr(scheduled_reports, "_rest_query", lambda *_args, **_kwargs: None)

    assert scheduled_reports._fetch_via_rest(date(2026, 4, 1), date(2026, 4, 14)) is None


def test_fetch_via_rest_keeps_gmv_spend_fallback_for_empty_detail(monkeypatch):
    def fake_rest_query(table, params=""):
        if table == "fact_spend_daily" and "channel=eq.meta" in params:
            return [{"spend": "100"}]
        if table == "fact_spend_daily" and "channel=eq.tiktok&" in params:
            return [{"spend": "300"}]
        if table == "fact_kpi_daily":
            return [{"revenue": "800", "orders": 10}]
        if table == "fact_tiktok_gmvmax_daily":
            return []
        if table == "fact_spend_daily" and "channel=eq.tiktok_gmvmax" in params:
            return [{"spend": "50"}]
        raise AssertionError(f"unexpected REST query: {table} {params}")

    monkeypatch.setattr(scheduled_reports, "_rest_query", fake_rest_query)

    data = scheduled_reports._fetch_via_rest(date(2026, 4, 1), date(2026, 4, 14))

    assert data["meta"]["purchase_value"] == 200
    assert data["tiktok_ads"]["purchase_value"] == 600
    assert data["gmv_max"]["spend"] == 50
    assert data["gmv_max"]["purchase_value"] == 0
