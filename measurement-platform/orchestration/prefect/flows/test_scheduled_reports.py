from datetime import date
import unittest
from unittest.mock import patch

from scheduled_reports import fetch_report_data


class ScheduledReportsFallbackTest(unittest.TestCase):
    def test_fetch_report_data_falls_back_when_pg_connect_raises(self):
        # Invalid DB URL should not crash the task; it should trigger REST fallback.
        rest_payload = {
            "meta": {"spend": 10.0, "purchase_value": 20.0, "roas": 2.0},
            "tiktok_ads": {"spend": 5.0, "purchase_value": 10.0, "roas": 2.0},
            "gmv_max": {"spend": 1.0, "purchase_value": 4.0, "roas": 4.0},
        }

        with patch.dict(
            "os.environ",
            {"SUPABASE_DB_URL": "postgresql://invalid-user:invalid-pass@invalid-host:5432/postgres"},
            clear=False,
        ), patch("scheduled_reports._fetch_via_rest", return_value=rest_payload) as rest_fetch:
            data = fetch_report_data.fn(date(2026, 4, 1), date(2026, 4, 14))

        self.assertEqual(data["meta"]["spend"], 10.0)
        self.assertEqual(data["gmv_max"]["roas"], 4.0)
        rest_fetch.assert_called_once()

