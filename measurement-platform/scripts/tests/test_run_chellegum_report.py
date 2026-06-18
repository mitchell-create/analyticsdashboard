import importlib.util
import pathlib
import unittest


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "run_chellegum_report.py"
)
SPEC = importlib.util.spec_from_file_location("run_chellegum_report", SCRIPT_PATH)
run_chellegum_report = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(run_chellegum_report)


class DummyCursor:
    def __init__(self, relkind):
        self.relkind = relkind
        self.commands = []

    def execute(self, sql, params=None):
        self.commands.append((sql, params))

    def fetchone(self):
        if self.relkind is None:
            return None
        return (self.relkind,)


def _commands_sql(cursor):
    return [sql for sql, _ in cursor.commands]


class ReplaceObjectSafetyTests(unittest.TestCase):
    def test_replace_refuses_table_without_force(self):
        cur = DummyCursor(relkind="r")

        with self.assertRaisesRegex(RuntimeError, "Refusing to replace public.fact_spend_daily"):
            run_chellegum_report._replace_public_object_with_view(
                cur=cur,
                object_name="fact_spend_daily",
                view_sql="CREATE OR REPLACE VIEW public.fact_spend_daily AS SELECT 1;",
                force_replace_tables=False,
            )

        sql_commands = _commands_sql(cur)
        self.assertFalse(any("DROP TABLE IF EXISTS public.fact_spend_daily" in sql for sql in sql_commands))

    def test_replace_drops_table_with_force(self):
        cur = DummyCursor(relkind="r")

        run_chellegum_report._replace_public_object_with_view(
            cur=cur,
            object_name="fact_spend_daily",
            view_sql="CREATE OR REPLACE VIEW public.fact_spend_daily AS SELECT 1;",
            force_replace_tables=True,
        )

        sql_commands = _commands_sql(cur)
        self.assertTrue(any("DROP TABLE IF EXISTS public.fact_spend_daily CASCADE;" in sql for sql in sql_commands))
        self.assertTrue(sql_commands[-1].startswith("CREATE OR REPLACE VIEW public.fact_spend_daily"))

    def test_replace_drops_existing_view(self):
        cur = DummyCursor(relkind="v")

        run_chellegum_report._replace_public_object_with_view(
            cur=cur,
            object_name="fact_spend_daily",
            view_sql="CREATE OR REPLACE VIEW public.fact_spend_daily AS SELECT 1;",
            force_replace_tables=False,
        )

        sql_commands = _commands_sql(cur)
        self.assertTrue(any("DROP VIEW IF EXISTS public.fact_spend_daily CASCADE;" in sql for sql in sql_commands))
        self.assertTrue(sql_commands[-1].startswith("CREATE OR REPLACE VIEW public.fact_spend_daily"))
