from datetime import date
import importlib.util
from pathlib import Path
import sys
import types


def _load_scheduled_reports_module():
    project_root = Path(__file__).resolve().parents[3]
    module_path = project_root / "orchestration" / "prefect" / "flows" / "scheduled_reports.py"
    spec = importlib.util.spec_from_file_location("scheduled_reports", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_get_pg_connection_returns_none_when_connect_raises(monkeypatch):
    module = _load_scheduled_reports_module()
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://invalid")

    fake_psycopg2 = types.SimpleNamespace(connect=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)

    assert module._get_pg_connection() is None


def test_fetch_report_data_falls_back_to_rest(monkeypatch):
    module = _load_scheduled_reports_module()

    class _Logger:
        def info(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(module, "get_run_logger", lambda: _Logger())

    calls = {"postgres": 0, "rest": 0}

    def _fake_postgres(_start, _end):
        calls["postgres"] += 1
        return None

    expected = {"meta": {"spend": 1}, "tiktok_ads": {"spend": 2}, "gmv_max": {"spend": 3}}

    def _fake_rest(_start, _end):
        calls["rest"] += 1
        return expected

    monkeypatch.setattr(module, "_fetch_via_postgres", _fake_postgres)
    monkeypatch.setattr(module, "_fetch_via_rest", _fake_rest)

    result = module.fetch_report_data.fn(date(2026, 3, 1), date(2026, 3, 14))

    assert result == expected
    assert calls == {"postgres": 1, "rest": 1}
