import importlib.util
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch


def _load_module():
    module_path = Path(__file__).with_name("scheduled_reports.py")
    spec = importlib.util.spec_from_file_location("scheduled_reports", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


scheduled_reports = _load_module()


class ScheduledReportsRestFailureTests(unittest.TestCase):
    def test_fetch_via_rest_returns_none_on_required_query_failure(self):
        with patch.object(scheduled_reports, "_rest_query", return_value=None):
            result = scheduled_reports._fetch_via_rest(date(2026, 4, 1), date(2026, 4, 14))

        self.assertIsNone(result)

    def test_fetch_via_rest_keeps_gmv_fallback_when_optional_query_fails(self):
        responses = [
            [{"spend": 100}],   # meta
            [{"spend": 50}],    # tiktok
            [{"revenue": 300}], # kpi
            None,               # optional GMV detail query fails
            [{"spend": 25}],    # GMV spend fallback from fact_spend_daily
        ]

        with patch.object(scheduled_reports, "_rest_query", side_effect=responses):
            result = scheduled_reports._fetch_via_rest(date(2026, 4, 1), date(2026, 4, 14))

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["gmv_max"]["spend"], 25.0)
        self.assertEqual(result["gmv_max"]["purchase_value"], 0)

    def test_fetch_report_data_returns_none_when_all_backends_fail(self):
        mock_logger = MagicMock()
        with patch.object(scheduled_reports, "get_run_logger", return_value=mock_logger):
            with patch.object(scheduled_reports, "_fetch_via_postgres", return_value=None):
                with patch.object(scheduled_reports, "_fetch_via_rest", return_value=None):
                    result = scheduled_reports.fetch_report_data.fn(date(2026, 4, 1), date(2026, 4, 14))

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
