import importlib.util
from pathlib import Path
from unittest.mock import Mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "run_chellegum_report.py"
spec = importlib.util.spec_from_file_location("run_chellegum_report", SCRIPT_PATH)
report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(report)


def test_setup_views_checks_public_tables_before_replacing_them(monkeypatch):
    cursor = Mock()
    cursor.fetchone.return_value = None
    connection = Mock()
    connection.cursor.return_value = cursor
    monkeypatch.setattr(report, "get_connection", lambda: connection)

    report.setup_views()

    assert cursor.execute.call_args_list[0].args[1] == ("fact_spend_daily",)
    assert cursor.execute.call_args_list[1].args[1] == ("fact_kpi_daily",)
    assert not any("DROP TABLE public.fact_spend_daily" in call.args[0] for call in cursor.execute.call_args_list)


def test_prepare_public_view_target_refuses_non_empty_table():
    cursor = Mock()
    cursor.fetchone.side_effect = [("r",), (True,)]

    try:
        report._prepare_public_view_target(cursor, "fact_spend_daily")
    except RuntimeError as exc:
        assert "Refusing to replace non-empty public.fact_spend_daily" in str(exc)
    else:
        raise AssertionError("expected non-empty table replacement to fail")
