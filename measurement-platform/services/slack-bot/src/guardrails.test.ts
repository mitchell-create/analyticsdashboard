import assert from "node:assert/strict";
import test from "node:test";

import { extractTablesUsed, isSqlAllowed } from "./guardrails";

test("allows queries that only use allowlisted relations", () => {
  const result = isSqlAllowed(
    "SELECT spend FROM public_marts.fact_spend_daily WHERE report_date >= CURRENT_DATE - INTERVAL '7 days'"
  );

  assert.equal(result.allowed, true);
});

test("blocks non-allowlisted relations in comma-separated FROM lists", () => {
  const result = isSqlAllowed(
    "SELECT * FROM public_marts.fact_spend_daily, private.customer_emails LIMIT 10"
  );

  assert.equal(result.allowed, false);
  assert.equal(result.reason, "Table not allowlisted: private.customer_emails");
});

test("audits every relation in comma-separated FROM lists", () => {
  assert.equal(
    extractTablesUsed(
      "SELECT * FROM public_marts.fact_spend_daily, public_marts.fact_kpi_daily LIMIT 10"
    ),
    "public_marts.fact_spend_daily, public_marts.fact_kpi_daily"
  );
});

test("does not split commas inside nested expressions", () => {
  const result = isSqlAllowed(
    "SELECT COALESCE(spend, 0) FROM public_marts.fact_spend_daily WHERE channel = 'meta'"
  );

  assert.equal(result.allowed, true);
});
