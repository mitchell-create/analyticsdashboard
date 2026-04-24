import importlib.util
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


def _load_scheduled_reports_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "flows"
        / "scheduled_reports.py"
    )
    spec = importlib.util.spec_from_file_location("scheduled_reports", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ScheduledReportsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_scheduled_reports_module()

    def test_rest_query_returns_none_when_key_missing(self):
        with patch.object(self.module, "SUPABASE_KEY", ""):
            rows = self.module._rest_query("fact_spend_daily", "select=spend")
        self.assertIsNone(rows)

    def test_rest_query_returns_none_on_http_error(self):
        fake_result = type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": '{"message":"forbidden"}\n401',
                "stderr": "",
            },
        )()
        with patch.object(self.module, "SUPABASE_KEY", "test-key"):
            with patch.object(self.module.subprocess, "run", return_value=fake_result):
                rows = self.module._rest_query("fact_spend_daily", "select=spend")
        self.assertIsNone(rows)

    def test_fetch_via_rest_returns_none_on_transport_failure(self):
        with patch.object(self.module, "_rest_query", return_value=None):
            data = self.module._fetch_via_rest(date(2026, 4, 1), date(2026, 4, 14))
        self.assertIsNone(data)

    def test_fetch_via_rest_keeps_zero_rows_as_valid(self):
        # Empty lists mean successful query with no matching rows (valid, not a transport/auth failure).
        side_effect = [[], [], [], [], []]
        with patch.object(self.module, "_rest_query", side_effect=side_effect):
            data = self.module._fetch_via_rest(date(2026, 4, 1), date(2026, 4, 14))
        self.assertIsNotNone(data)
        self.assertEqual(data["meta"]["spend"], 0)
        self.assertEqual(data["tiktok_ads"]["spend"], 0)
        self.assertEqual(data["gmv_max"]["spend"], 0)


if __name__ == "__main__":
    unittest.main()
