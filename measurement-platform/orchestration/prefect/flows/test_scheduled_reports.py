import importlib.util
import os
import pathlib
import sys
import types
import unittest
from datetime import date
from unittest.mock import patch


def _load_scheduled_reports_module():
    """Load scheduled_reports.py with lightweight Prefect stubs."""
    if "prefect" not in sys.modules:
        prefect_stub = types.ModuleType("prefect")

        def _decorator(*_args, **_kwargs):
            def _wrap(func):
                return func

            return _wrap

        prefect_stub.flow = _decorator
        prefect_stub.task = _decorator
        sys.modules["prefect"] = prefect_stub

    if "prefect.logging" not in sys.modules:
        prefect_logging_stub = types.ModuleType("prefect.logging")

        class _Logger:
            def info(self, *_args, **_kwargs):
                return None

        prefect_logging_stub.get_run_logger = lambda: _Logger()
        sys.modules["prefect.logging"] = prefect_logging_stub

    module_path = pathlib.Path(__file__).with_name("scheduled_reports.py")
    spec = importlib.util.spec_from_file_location("scheduled_reports_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _FakeHttpResponse:
    def __init__(self, payload: str):
        self._payload = payload

    def read(self):
        return self._payload.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False


class ScheduledReportsRestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_scheduled_reports_module()

    def test_rest_query_returns_none_on_transport_error(self):
        with patch.dict(
            os.environ,
            {"SUPABASE_SERVICE_KEY": "test-key", "SUPABASE_URL": "https://example.test"},
            clear=False,
        ):
            with patch.object(
                self.module.urllib_request,
                "urlopen",
                side_effect=self.module.urllib_error.URLError("network failure"),
            ):
                rows = self.module._rest_query("fact_spend_daily", "select=spend")
        self.assertIsNone(rows)

    def test_rest_query_reads_json_list_successfully(self):
        with patch.dict(
            os.environ,
            {"SUPABASE_SERVICE_KEY": "test-key", "SUPABASE_URL": "https://example.test"},
            clear=False,
        ):
            with patch.object(
                self.module.urllib_request,
                "urlopen",
                return_value=_FakeHttpResponse('[{"spend":"12.34"}]'),
            ):
                rows = self.module._rest_query("fact_spend_daily", "select=spend")
        self.assertEqual(rows, [{"spend": "12.34"}])

    def test_fetch_via_rest_fails_closed_when_query_fails(self):
        with patch.object(self.module, "_rest_query", return_value=None):
            data = self.module._fetch_via_rest(date(2026, 3, 1), date(2026, 3, 31))
        self.assertIsNone(data)


if __name__ == "__main__":
    unittest.main()
