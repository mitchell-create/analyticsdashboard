import importlib.util
import sys
import types
import unittest
from datetime import date
from pathlib import Path


def _load_scheduled_reports_module():
    # Provide tiny Prefect stubs so we can import the flow module in unit tests
    # without requiring Prefect to be installed in the test environment.
    prefect_stub = types.ModuleType("prefect")
    prefect_stub.flow = lambda *args, **kwargs: (lambda fn: fn)
    prefect_stub.task = lambda *args, **kwargs: (lambda fn: fn)

    prefect_logging_stub = types.ModuleType("prefect.logging")

    class _Logger:
        def info(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

    prefect_logging_stub.get_run_logger = lambda: _Logger()

    sys.modules.setdefault("prefect", prefect_stub)
    sys.modules.setdefault("prefect.logging", prefect_logging_stub)

    module_path = Path(__file__).with_name("scheduled_reports.py")
    spec = importlib.util.spec_from_file_location("scheduled_reports", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ScheduledReportsTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_scheduled_reports_module()

    def test_rest_fetch_aborts_when_gmv_revenue_source_missing(self):
        def fake_rest_query(table: str, params: str = ""):
            if table == "fact_spend_daily" and "channel=eq.meta" in params:
                return [{"spend": 100}]
            if table == "fact_spend_daily" and "channel=eq.tiktok" in params:
                return [{"spend": 50}]
            if table == "fact_kpi_daily":
                return [{"revenue": 300, "orders": 10}]
            if table == "fact_tiktok_gmvmax_daily":
                # Simulate stale/misconfigured view returning no GMV revenue rows.
                return []
            if table == "fact_spend_daily" and "channel=eq.tiktok_gmvmax" in params:
                # Spend exists for GMV Max in fact_spend_daily.
                return [{"spend": 200}]
            return []

        self.mod._rest_query = fake_rest_query

        result = self.mod._fetch_via_rest(date(2026, 3, 1), date(2026, 3, 31))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
