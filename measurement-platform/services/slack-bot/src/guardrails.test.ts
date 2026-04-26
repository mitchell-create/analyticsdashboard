import assert from "node:assert/strict";
import test from "node:test";

import { extractTablesUsed, isSqlAllowed } from "./guardrails";

test("allows queries that only use allowlisted tables", () => {
  const result = isSqlAllowed(
    "SELECT report_date, spend FROM public_marts.fact_spend_daily LIMIT 10"
  );

  assert.equal(result.allowed, true);
});

test("blocks non-allowlisted tables in comma-separated FROM lists", () => {
  const result = isSqlAllowed(
    "SELECT * FROM public_marts.fact_spend_daily, private.customer_emails LIMIT 10"
  );

  assert.equal(result.allowed, false);
  assert.equal(result.reason, "Table not allowlisted: private.customer_emails");
});

test("blocks SELECT statements that do not reference an allowlisted table", () => {
  const result = isSqlAllowed("SELECT pg_sleep(10)");

  assert.equal(result.allowed, false);
});

test("extracts all tables from joins and comma-separated FROM lists", () => {
  const tables = extractTablesUsed(
    "SELECT * FROM public_marts.fact_spend_daily fs, public_marts.fact_kpi_daily fk JOIN public_marts.dim_geo dg ON dg.geo_id = fk.geo_id"
  );

  assert.equal(
    tables,
    "public_marts.fact_spend_daily, public_marts.fact_kpi_daily, public_marts.dim_geo"
  );
});
