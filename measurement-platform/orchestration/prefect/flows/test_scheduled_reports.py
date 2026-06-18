import importlib.util
import os
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("scheduled_reports.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("scheduled_reports", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _DummyLogger:
    def info(self, *_args, **_kwargs):
        return None


class ScheduledReportsTests(unittest.TestCase):
    def test_get_pg_connection_returns_none_when_connect_raises(self):
        module = _load_module()

        fake_psycopg2 = types.SimpleNamespace(
            connect=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db down"))
        )

        with patch.dict(os.environ, {"SUPABASE_DB_URL": "postgresql://fake"}, clear=False):
            with patch.dict(sys.modules, {"psycopg2": fake_psycopg2}):
                conn = module._get_pg_connection()

        self.assertIsNone(conn)

    def test_fetch_report_data_falls_back_to_rest(self):
        module = _load_module()
        fallback_payload = {
            "meta": {"spend": 10},
            "tiktok_ads": {"spend": 20},
            "gmv_max": {"spend": 30},
        }

        with patch.object(module, "_fetch_via_postgres", return_value=None):
            with patch.object(module, "_fetch_via_rest", return_value=fallback_payload):
                with patch.object(module, "get_run_logger", return_value=_DummyLogger()):
                    result = module.fetch_report_data.fn(date(2026, 3, 1), date(2026, 3, 14))

        self.assertEqual(result, fallback_payload)


if __name__ == "__main__":
    unittest.main()
