import assert from "node:assert/strict";
import { isSqlAllowed } from "./guardrails";

function expectAllowed(sql: string): void {
  const result = isSqlAllowed(sql);
  assert.equal(result.allowed, true, `Expected allowed but got blocked: ${result.reason ?? "unknown"}`);
}

function expectBlocked(sql: string, reasonIncludes: string): void {
  const result = isSqlAllowed(sql);
  assert.equal(result.allowed, false, `Expected blocked but query was allowed: ${sql}`);
  assert.ok(result.reason?.includes(reasonIncludes), `Expected reason to include "${reasonIncludes}", got "${result.reason ?? ""}"`);
}

function run(): void {
  expectAllowed("SELECT report_date, spend FROM public_marts.fact_spend_daily LIMIT 10");
  expectAllowed("SELECT f.report_date, g.geo_name FROM public_marts.fact_kpi_geo_daily f JOIN public_marts.dim_geo g ON f.geo_id = g.geo_id");

  expectBlocked("SELECT now()", "must reference at least one allowlisted table");
  expectBlocked("SELECT pg_sleep(5)", "forbidden function");
  expectBlocked("SELECT pg_read_file('/etc/passwd')", "forbidden function");
  expectBlocked("SELECT * FROM pg_catalog.pg_tables", "Table not allowlisted");
  expectBlocked("WITH t AS (SELECT 1) SELECT * FROM t", "Only SELECT queries are allowed");
}

run();
console.log("guardrails tests passed");
