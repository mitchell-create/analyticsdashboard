const test = require("node:test");
const assert = require("node:assert/strict");

const { isSqlAllowed, extractTablesUsed } = require("../dist/guardrails");

test("allows query against allowlisted table", () => {
  const sql = "SELECT report_date, revenue FROM public_marts.fact_kpi_daily LIMIT 5";
  const result = isSqlAllowed(sql);
  assert.equal(result.allowed, true);
});

test("blocks explicit non-allowlisted join table", () => {
  const sql = `
    SELECT k.report_date
    FROM public_marts.fact_kpi_daily k
    JOIN private.payroll p ON p.report_date = k.report_date
  `;
  const result = isSqlAllowed(sql);
  assert.equal(result.allowed, false);
  assert.match(result.reason || "", /not allowlisted/i);
});

test("blocks implicit comma join bypass to non-allowlisted table", () => {
  const sql = `
    SELECT k.report_date
    FROM public_marts.fact_kpi_daily k, private.payroll p
    WHERE p.report_date = k.report_date
  `;
  const result = isSqlAllowed(sql);
  assert.equal(result.allowed, false);
  assert.match(result.reason || "", /private\.payroll/i);
});

test("extractTablesUsed includes comma-joined tables", () => {
  const sql = `
    SELECT k.report_date
    FROM public_marts.fact_kpi_daily k, private.payroll p
    WHERE p.report_date = k.report_date
  `;
  const tables = extractTablesUsed(sql);
  assert.equal(tables, "public_marts.fact_kpi_daily, private.payroll");
});

test("does not falsely block allowlisted table in subquery", () => {
  const sql = `
    SELECT x.report_date
    FROM (
      SELECT report_date FROM public_marts.fact_spend_daily
    ) x
    LIMIT 3
  `;
  const result = isSqlAllowed(sql);
  assert.equal(result.allowed, true);
});
