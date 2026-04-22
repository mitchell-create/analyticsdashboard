import assert from "node:assert/strict";
import test from "node:test";

import { extractTablesUsed, isSqlAllowed } from "./guardrails";

test("allows query against allowlisted marts table", () => {
  const sql = "SELECT report_date, spend FROM public_marts.fact_spend_daily LIMIT 10";
  const result = isSqlAllowed(sql);
  assert.equal(result.allowed, true);
});

test("blocks comma-join query that references non-allowlisted table", () => {
  const sql =
    "SELECT u.email FROM public_marts.fact_spend_daily f, auth.users u WHERE f.report_date = CURRENT_DATE LIMIT 5";
  const result = isSqlAllowed(sql);
  assert.equal(result.allowed, false);
  assert.match(result.reason ?? "", /auth\.users/);
});

test("extractTablesUsed returns all tables including comma-separated refs", () => {
  const sql =
    "SELECT * FROM public_marts.fact_spend_daily f, public_marts.fact_kpi_daily k JOIN public_marts.dim_geo g ON true";
  assert.equal(
    extractTablesUsed(sql),
    "public_marts.fact_spend_daily, public_marts.fact_kpi_daily, public_marts.dim_geo"
  );
});
