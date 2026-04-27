import importlib.util
import sys
import types
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import patch


class _Task:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, *args, **kwargs):
        return self.fn(*args, **kwargs)

    def submit(self, *args, **kwargs):
        return types.SimpleNamespace(result=lambda: self.fn(*args, **kwargs))


def _load_module():
    prefect = types.ModuleType("prefect")
    prefect.flow = lambda **_kwargs: lambda fn: fn
    prefect.task = lambda fn: _Task(fn)

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


def _load_report_script():
    module_path = Path(__file__).parents[3] / "scripts" / "run_chellegum_report.py"
    spec = importlib.util.spec_from_file_location("run_chellegum_report", module_path)
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
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b"not json"

        with patch.object(self.reports.urllib.request, "urlopen", return_value=Response()):
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


class ReportSetupViewsTest(unittest.TestCase):
    def setUp(self):
        self.script = _load_report_script()

    def test_setup_views_checks_for_non_empty_public_tables_before_drop(self):
        executed = []

        class Cursor:
            def execute(self, sql):
                executed.append(sql)

            def close(self):
                pass

        class Connection:
            def cursor(self):
                return Cursor()

            def commit(self):
                pass

            def close(self):
                pass

        with patch.object(self.script, "get_connection", return_value=Connection()):
            self.script.setup_views()

        self.assertEqual(executed[0], self.script.NON_EMPTY_PUBLIC_TABLE_GUARD_SQL)
        self.assertIn("SELECT count(*) FROM public.%I", executed[0])
        self.assertIn("RAISE EXCEPTION 'Refusing to drop non-empty public.% table", executed[0])
        self.assertEqual(executed[1], "DROP TABLE IF EXISTS public.fact_spend_daily CASCADE;")


if __name__ == "__main__":
    unittest.main()
