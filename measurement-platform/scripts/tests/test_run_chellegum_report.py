import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "run_chellegum_report.py"


spec = importlib.util.spec_from_file_location("run_chellegum_report", SCRIPT_PATH)
run_chellegum_report = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(run_chellegum_report)


def test_replace_empty_table_guard_refuses_non_empty_tables():
    sql = run_chellegum_report._replace_empty_table_guard_sql("fact_spend_daily")

    assert "existing_kind IN ('r', 'p', 'f')" in sql
    assert "SELECT count(*) FROM public.fact_spend_daily" in sql
    assert "existing_rows > 0" in sql
    assert "Refusing to replace non-empty public.fact_spend_daily table with a view" in sql


def test_replace_empty_table_guard_rejects_unexpected_names():
    try:
        run_chellegum_report._replace_empty_table_guard_sql("fact_spend_daily; drop schema public")
    except ValueError as exc:
        assert "Unexpected public view name" in str(exc)
    else:
        raise AssertionError("Expected unexpected view names to be rejected")
