import importlib.util
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _load_scheduled_reports_module():
    # Keep tests independent from Prefect installation.
    fake_prefect = types.ModuleType("prefect")
    fake_prefect.flow = lambda *args, **kwargs: (lambda fn: fn)
    fake_prefect.task = lambda *args, **kwargs: (lambda fn: fn)

    fake_prefect_logging = types.ModuleType("prefect.logging")
    fake_prefect_logging.get_run_logger = lambda: SimpleNamespace(info=lambda *_: None, warning=lambda *_: None)

    sys.modules.setdefault("prefect", fake_prefect)
    sys.modules.setdefault("prefect.logging", fake_prefect_logging)

    path = Path(__file__).resolve().parents[1] / "flows" / "scheduled_reports.py"
    spec = importlib.util.spec_from_file_location("scheduled_reports_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ScheduledReportsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_scheduled_reports_module()

    def test_rest_query_returns_none_on_curl_failure(self):
        with patch.object(self.mod, "SUPABASE_KEY", "key"), patch.object(
            self.mod.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=28, stdout="", stderr="timeout"),
        ):
            self.assertIsNone(self.mod._rest_query("fact_spend_daily"))

    def test_rest_query_returns_none_on_non_2xx(self):
        with patch.object(self.mod, "SUPABASE_KEY", "key"), patch.object(
            self.mod.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout='{"message":"boom"}\n500', stderr=""),
        ):
            self.assertIsNone(self.mod._rest_query("fact_spend_daily"))

    def test_rest_query_returns_rows_on_2xx(self):
        with patch.object(self.mod, "SUPABASE_KEY", "key"), patch.object(
            self.mod.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout='[{"spend":"12.50"}]\n200', stderr=""),
        ):
            rows = self.mod._rest_query("fact_spend_daily")
        self.assertEqual(rows, [{"spend": "12.50"}])

    def test_fetch_via_rest_fails_closed_when_required_query_fails(self):
        with patch.object(self.mod, "_rest_query", side_effect=[None]):
            data = self.mod._fetch_via_rest(date(2026, 3, 1), date(2026, 3, 14))
        self.assertIsNone(data)

    def test_fetch_via_rest_uses_gmv_fallback_when_detail_empty(self):
        side_effect = [
            [{"spend": 100}],  # meta
            [{"spend": 50}],   # tiktok
            [{"revenue": 300}],  # kpi
            [],  # gmv detail
            [{"spend": 80}],  # gmv fallback from fact_spend_daily
        ]
        with patch.object(self.mod, "_rest_query", side_effect=side_effect):
            data = self.mod._fetch_via_rest(date(2026, 3, 1), date(2026, 3, 14))

        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data["meta"]["spend"], 100)
        self.assertEqual(data["tiktok_ads"]["spend"], 50)
        self.assertEqual(data["gmv_max"]["spend"], 80)
        self.assertEqual(data["gmv_max"]["purchase_value"], 0)


if __name__ == "__main__":
    unittest.main()
