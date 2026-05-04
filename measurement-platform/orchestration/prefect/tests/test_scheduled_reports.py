import importlib.util
import json
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from urllib.error import URLError


def load_scheduled_reports():
    prefect = types.ModuleType("prefect")
    prefect.flow = lambda *args, **kwargs: (lambda fn: fn)
    prefect.task = lambda *args, **kwargs: (lambda fn: fn)

    prefect_logging = types.ModuleType("prefect.logging")
    prefect_logging.get_run_logger = lambda: types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )

    sys.modules["prefect"] = prefect
    sys.modules["prefect.logging"] = prefect_logging

    module_path = (
        Path(__file__).resolve().parents[1] / "flows" / "scheduled_reports.py"
    )
    spec = importlib.util.spec_from_file_location("scheduled_reports", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class ScheduledReportsTests(unittest.TestCase):
    def test_rest_query_uses_https_client_and_returns_rows(self):
        module = load_scheduled_reports()
        module.SUPABASE_KEY = "service-key"
        module.SUPABASE_URL = "https://example.supabase.co"
        seen = {}

        def fake_urlopen(request, timeout):
            seen["url"] = request.full_url
            seen["headers"] = dict(request.header_items())
            seen["timeout"] = timeout
            return FakeResponse([{"spend": 12.34}])

        module.urlopen = fake_urlopen

        rows = module._rest_query("fact_spend_daily", "select=spend")

        self.assertEqual(rows, [{"spend": 12.34}])
        self.assertEqual(seen["url"], "https://example.supabase.co/rest/v1/fact_spend_daily?select=spend")
        self.assertEqual(seen["headers"]["Apikey"], "service-key")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer service-key")
        self.assertEqual(seen["timeout"], 15)
        self.assertFalse(hasattr(module, "subprocess"))

    def test_rest_query_returns_none_on_transport_failure(self):
        module = load_scheduled_reports()
        module.SUPABASE_KEY = "service-key"
        module.urlopen = lambda request, timeout: (_ for _ in ()).throw(URLError("down"))

        self.assertIsNone(module._rest_query("fact_spend_daily", "select=spend"))

    def test_rest_fallback_aborts_on_required_query_failure(self):
        module = load_scheduled_reports()
        module._rest_query = lambda table, params="": None

        data = module._fetch_via_rest(date(2026, 4, 1), date(2026, 4, 14))

        self.assertIsNone(data)

    def test_rest_fallback_preserves_gmv_spend_only_fallback(self):
        module = load_scheduled_reports()
        responses = iter(
            [
                [{"spend": 100}],
                [{"spend": 50}],
                [{"revenue": 300}],
                [],
                [{"spend": 25}],
            ]
        )
        module._rest_query = lambda table, params="": next(responses)

        data = module._fetch_via_rest(date(2026, 4, 1), date(2026, 4, 14))

        self.assertEqual(data["meta"]["spend"], 100)
        self.assertEqual(data["tiktok_ads"]["spend"], 50)
        self.assertEqual(data["gmv_max"]["spend"], 25)
        self.assertEqual(data["gmv_max"]["purchase_value"], 0)


if __name__ == "__main__":
    unittest.main()
