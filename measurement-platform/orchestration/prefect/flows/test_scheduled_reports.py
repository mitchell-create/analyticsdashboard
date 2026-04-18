from datetime import date
import unittest
from unittest.mock import patch

import scheduled_reports


class ScheduledReportsFallbackTest(unittest.TestCase):
    def test_fetch_report_data_falls_back_when_pg_connect_raises(self):
        # Invalid DB URL should not crash the task; it should trigger REST fallback.
        rest_payload = {
            "meta": {"spend": 10.0, "purchase_value": 20.0, "roas": 2.0},
            "tiktok_ads": {"spend": 5.0, "purchase_value": 10.0, "roas": 2.0},
            "gmv_max": {"spend": 1.0, "purchase_value": 4.0, "roas": 4.0},
        }

        logger = type("LoggerStub", (), {"info": lambda *_args, **_kwargs: None})()
        with patch("scheduled_reports._fetch_via_postgres", return_value=None), patch(
            "scheduled_reports._fetch_via_rest", return_value=rest_payload
        ) as rest_fetch, patch("scheduled_reports.get_run_logger", return_value=logger):
            data = scheduled_reports.fetch_report_data.fn(date(2026, 4, 1), date(2026, 4, 14))

        self.assertEqual(data["meta"]["spend"], 10.0)
        self.assertEqual(data["gmv_max"]["roas"], 4.0)
        rest_fetch.assert_called_once()

    def test_fetch_via_postgres_returns_none_when_connection_raises(self):
        logger = type("LoggerStub", (), {"warning": lambda *_args, **_kwargs: None})()
        with patch(
            "scheduled_reports._get_pg_connection", side_effect=RuntimeError("connection boom")
        ), patch("scheduled_reports.get_run_logger", return_value=logger):
            data = scheduled_reports._fetch_via_postgres(date(2026, 4, 1), date(2026, 4, 14))

        self.assertIsNone(data)

