import assert from "node:assert/strict";
import { isSqlAllowed } from "./guardrails";

function expectAllowed(sql: string): void {
  const result = isSqlAllowed(sql);
  assert.equal(result.allowed, true, `Expected allowed SQL, got: ${result.reason ?? "blocked"}`);
}

function expectBlocked(sql: string, reasonIncludes: string): void {
  const result = isSqlAllowed(sql);
  assert.equal(result.allowed, false, "Expected SQL to be blocked");
  assert.ok(result.reason?.includes(reasonIncludes), `Expected reason to include "${reasonIncludes}", got "${result.reason}"`);
}

expectAllowed("SELECT report_date, spend FROM public_marts.fact_spend_daily LIMIT 10");
expectAllowed('SELECT * FROM "public_marts"."fact_kpi_daily" LIMIT 1;');

expectBlocked("SELECT pg_sleep(5)", "dangerous database function");
expectBlocked("SELECT 1", "must reference an allowlisted table");
expectBlocked("SELECT * FROM public_marts.fact_spend_daily; SELECT 1", "Multiple SQL statements");
expectBlocked("SELECT * FROM pg_catalog.pg_tables", "Table not allowlisted");

console.log("guardrails.test.ts: all assertions passed");
