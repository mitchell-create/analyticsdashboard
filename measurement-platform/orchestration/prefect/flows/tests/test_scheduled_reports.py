import importlib.util
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scheduled_reports.py"
SPEC = importlib.util.spec_from_file_location("scheduled_reports", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load module from {MODULE_PATH}")
scheduled_reports = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scheduled_reports)


class ScheduledReportsRestFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        scheduled_reports.SUPABASE_KEY = "test-key"
        scheduled_reports.SUPABASE_URL = "https://example.supabase.co"

    def test_rest_query_returns_none_for_non_list_json(self) -> None:
        fake_result = SimpleNamespace(returncode=0, stdout='{"message":"error"}')
        with patch.object(scheduled_reports.subprocess, "run", return_value=fake_result):
            rows = scheduled_reports._rest_query("fact_spend_daily", "select=spend")
        self.assertIsNone(rows)

    def test_fetch_via_rest_returns_none_when_required_query_fails(self) -> None:
        with patch.object(scheduled_reports, "_rest_query", side_effect=[None]):
            data = scheduled_reports._fetch_via_rest(date(2026, 3, 1), date(2026, 3, 31))
        self.assertIsNone(data)

    def test_fetch_via_rest_returns_none_when_gmv_fallback_query_fails(self) -> None:
        query_results = [
            [{"spend": 100}],  # meta
            [{"spend": 50}],   # tiktok
            [{"revenue": 300}],  # kpi
            [],  # gmv_detail missing -> fallback
            None,  # fallback fact_spend_daily query failed
        ]
        with patch.object(scheduled_reports, "_rest_query", side_effect=query_results):
            data = scheduled_reports._fetch_via_rest(date(2026, 3, 1), date(2026, 3, 31))
        self.assertIsNone(data)

    def test_fetch_via_rest_allows_successful_empty_results(self) -> None:
        query_results = [
            [],  # meta
            [],  # tiktok
            [],  # kpi
            [],  # gmv_detail missing -> fallback
            [],  # fallback gmv spend query: successful but no rows
        ]
        with patch.object(scheduled_reports, "_rest_query", side_effect=query_results):
            data = scheduled_reports._fetch_via_rest(date(2026, 3, 1), date(2026, 3, 31))

        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data["meta"]["spend"], 0)
        self.assertEqual(data["tiktok_ads"]["spend"], 0)
        self.assertEqual(data["gmv_max"]["spend"], 0)


if __name__ == "__main__":
    unittest.main()
