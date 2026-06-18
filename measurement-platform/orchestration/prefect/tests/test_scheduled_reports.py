import importlib.util
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "flows" / "scheduled_reports.py"
SPEC = importlib.util.spec_from_file_location("scheduled_reports", MODULE_PATH)
scheduled_reports = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(scheduled_reports)


class ScheduledReportsRestFallbackTests(unittest.TestCase):
    def test_fetch_via_rest_returns_none_when_core_query_fails(self):
        def fake_rest_query(table: str, params: str = ""):
            if table == "fact_spend_daily" and "channel=eq.meta" in params:
                return None
            return []

        with patch.object(scheduled_reports, "_rest_query", side_effect=fake_rest_query):
            data = scheduled_reports._fetch_via_rest(date(2026, 3, 1), date(2026, 3, 14))

        self.assertIsNone(data)

    def test_fetch_via_rest_uses_spend_fallback_when_gmv_detail_missing(self):
        def fake_rest_query(table: str, params: str = ""):
            if table == "fact_spend_daily" and "channel=eq.meta" in params:
                return [{"spend": 100}]
            if table == "fact_spend_daily" and "channel=eq.tiktok&" in params:
                return [{"spend": 300}]
            if table == "fact_spend_daily" and "channel=eq.tiktok_gmvmax" in params:
                return [{"spend": 50}]
            if table == "fact_kpi_daily":
                return [{"revenue": 800, "orders": 10}]
            if table == "fact_tiktok_gmvmax_daily":
                # Simulate relation missing / inaccessible for the dedicated GMV table.
                return None
            raise AssertionError(f"Unexpected query: table={table}, params={params}")

        with patch.object(scheduled_reports, "_rest_query", side_effect=fake_rest_query):
            data = scheduled_reports._fetch_via_rest(date(2026, 3, 1), date(2026, 3, 14))

        self.assertIsNotNone(data)
        assert data is not None
        self.assertAlmostEqual(data["meta"]["spend"], 100)
        self.assertAlmostEqual(data["meta"]["purchase_value"], 200)
        self.assertAlmostEqual(data["tiktok_ads"]["spend"], 300)
        self.assertAlmostEqual(data["tiktok_ads"]["purchase_value"], 600)
        self.assertAlmostEqual(data["gmv_max"]["spend"], 50)
        self.assertAlmostEqual(data["gmv_max"]["purchase_value"], 0)


if __name__ == "__main__":
    unittest.main()
