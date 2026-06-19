from datetime import date

from flows import scheduled_reports


def test_fetch_via_rest_returns_none_when_gmv_detail_missing_but_spend_exists(monkeypatch):
    """Prevent silent GMV revenue drop when GMV detail view is unavailable."""

    def fake_rest_query(table: str, params: str = "") -> list[dict]:
        if table == "fact_spend_daily" and "channel=eq.meta" in params:
            return [{"spend": "100"}]
        if table == "fact_spend_daily" and "channel=eq.tiktok" in params:
            return [{"spend": "100"}]
        if table == "fact_kpi_daily":
            return [{"revenue": "500", "orders": "5"}]
        if table == "fact_tiktok_gmvmax_daily":
            return []
        if table == "fact_spend_daily" and "channel=eq.tiktok_gmvmax" in params:
            return [{"spend": "250"}]
        return []

    monkeypatch.setattr(scheduled_reports, "_rest_query", fake_rest_query)

    result = scheduled_reports._fetch_via_rest(date(2026, 3, 1), date(2026, 3, 14))
    assert result is None

