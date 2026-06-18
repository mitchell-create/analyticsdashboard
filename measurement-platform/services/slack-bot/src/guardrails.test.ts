import test from "node:test";
import assert from "node:assert/strict";
import { isSqlAllowed } from "./guardrails";

test("allows select query against allowlisted table", () => {
  const result = isSqlAllowed(
    "SELECT report_date, revenue FROM public_marts.fact_kpi_daily LIMIT 10"
  );
  assert.equal(result.allowed, true);
});

test("blocks select queries without a referenced table", () => {
  const result = isSqlAllowed("SELECT pg_sleep(5)");
  assert.equal(result.allowed, false);
  assert.match(result.reason ?? "", /must reference allowlisted tables|forbidden function/i);
});

test("blocks dangerous postgres function calls", () => {
  const result = isSqlAllowed(
    "SELECT pg_sleep(5) FROM public_marts.fact_kpi_daily LIMIT 1"
  );
  assert.equal(result.allowed, false);
  assert.match(result.reason ?? "", /forbidden function/i);
});

test("blocks multi-statement select payloads", () => {
  const result = isSqlAllowed(
    "SELECT report_date FROM public_marts.fact_kpi_daily LIMIT 1; SELECT pg_sleep(5)"
  );
  assert.equal(result.allowed, false);
  assert.match(result.reason ?? "", /multiple statements/i);
});

test("blocks non-allowlisted tables", () => {
  const result = isSqlAllowed("SELECT * FROM pg_catalog.pg_tables");
  assert.equal(result.allowed, false);
  assert.match(result.reason ?? "", /not allowlisted/i);
});
