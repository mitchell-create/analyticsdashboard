import importlib.util
import pathlib
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = pathlib.Path(__file__).with_name("scheduled_reports.py")
SPEC = importlib.util.spec_from_file_location("scheduled_reports", MODULE_PATH)
scheduled_reports = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(scheduled_reports)


class ScheduledReportsRestFallbackTests(unittest.TestCase):
    def test_rest_query_returns_none_without_service_key(self) -> None:
        with patch.object(scheduled_reports, "SUPABASE_KEY", ""):
            rows = scheduled_reports._rest_query("fact_spend_daily", "select=spend")
        self.assertIsNone(rows)

    def test_rest_query_returns_rows_on_http_200_list_payload(self) -> None:
        curl_result = SimpleNamespace(returncode=0, stdout='[{"spend":"12.34"}]\n200')
        with patch.object(scheduled_reports, "SUPABASE_KEY", "test-key"):
            with patch.object(scheduled_reports.subprocess, "run", return_value=curl_result):
                rows = scheduled_reports._rest_query("fact_spend_daily", "select=spend")
        self.assertEqual(rows, [{"spend": "12.34"}])

    def test_fetch_via_rest_returns_none_on_required_query_failure(self) -> None:
        with patch.object(scheduled_reports, "_rest_query", return_value=None):
            data = scheduled_reports._fetch_via_rest(date(2026, 3, 1), date(2026, 3, 14))
        self.assertIsNone(data)

    def test_fetch_via_rest_tolerates_missing_optional_gmv_detail_table(self) -> None:
        responses = [
            [{"spend": "10"}],  # meta
            [{"spend": "30"}],  # tiktok
            [{"revenue": "80", "orders": "5"}],  # kpi
            None,  # gmv detail table missing/unavailable
            [{"spend": "20"}],  # gmv spend fallback
        ]
        with patch.object(scheduled_reports, "_rest_query", side_effect=responses):
            data = scheduled_reports._fetch_via_rest(date(2026, 3, 1), date(2026, 3, 14))
        self.assertIsNotNone(data)
        self.assertEqual(data["meta"]["spend"], 10.0)
        self.assertEqual(data["tiktok_ads"]["spend"], 30.0)
        self.assertEqual(data["gmv_max"]["spend"], 20.0)
        self.assertEqual(data["gmv_max"]["purchase_value"], 0)


if __name__ == "__main__":
    unittest.main()
