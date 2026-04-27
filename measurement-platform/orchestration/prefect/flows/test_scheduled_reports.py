import importlib.util
import json
import sys
import types
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import patch


def _load_module():
    prefect = types.ModuleType("prefect")
    prefect.flow = lambda **_kwargs: lambda fn: fn
    prefect.task = lambda fn: fn

    logging = types.ModuleType("prefect.logging")
    logging.get_run_logger = lambda: types.SimpleNamespace(info=lambda *_args, **_kwargs: None)

    sys.modules["prefect"] = prefect
    sys.modules["prefect.logging"] = logging

    module_path = Path(__file__).with_name("scheduled_reports.py")
    spec = importlib.util.spec_from_file_location("scheduled_reports", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ScheduledReportRestFallbackTest(unittest.TestCase):
    def setUp(self):
        self.reports = _load_module()
        self.reports.SUPABASE_KEY = "service-key"

    def test_rest_query_returns_none_on_transport_error(self):
        with patch.object(
            self.reports.urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            self.assertIsNone(self.reports._rest_query("fact_spend_daily"))

    def test_rest_query_returns_none_on_invalid_json(self):
        response = types.SimpleNamespace(
            __enter__=lambda self: self,
            __exit__=lambda *_args: None,
            read=lambda: b"not json",
        )

        with patch.object(self.reports.urllib.request, "urlopen", return_value=response):
            self.assertIsNone(self.reports._rest_query("fact_spend_daily"))

    def test_fetch_via_rest_fails_closed_when_required_query_fails(self):
        def fake_rest_query(table, params=""):
            if table == "fact_kpi_daily":
                return None
            return []

        with patch.object(self.reports, "_rest_query", side_effect=fake_rest_query):
            self.assertIsNone(
                self.reports._fetch_via_rest(date(2026, 4, 1), date(2026, 4, 14))
            )

    def test_fetch_via_rest_allows_empty_gmv_detail_with_spend_fallback(self):
        def fake_rest_query(table, params=""):
            if table == "fact_spend_daily" and "channel=eq.meta" in params:
                return [{"spend": 100}]
            if table == "fact_spend_daily" and "channel=eq.tiktok&" in params:
                return [{"spend": 50}]
            if table == "fact_kpi_daily":
                return [{"revenue": 300, "orders": 3}]
            if table == "fact_tiktok_gmvmax_daily":
                return []
            if table == "fact_spend_daily" and "channel=eq.tiktok_gmvmax" in params:
                return [{"spend": 25}]
            raise AssertionError(f"unexpected query: {table} {params}")

        with patch.object(self.reports, "_rest_query", side_effect=fake_rest_query):
            data = self.reports._fetch_via_rest(date(2026, 4, 1), date(2026, 4, 14))

        self.assertEqual(data["meta"]["spend"], 100)
        self.assertEqual(data["tiktok_ads"]["spend"], 50)
        self.assertEqual(data["gmv_max"]["spend"], 25)
        self.assertEqual(data["gmv_max"]["purchase_value"], 0)


if __name__ == "__main__":
    unittest.main()
