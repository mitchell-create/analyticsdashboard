import test from "node:test";
import assert from "node:assert/strict";

import { isSqlAllowed } from "../guardrails";

test("allows simple SELECT against allowlisted marts table", () => {
  const result = isSqlAllowed(
    "SELECT report_date, spend FROM public_marts.fact_spend_daily LIMIT 10"
  );
  assert.equal(result.allowed, true);
});

test("blocks queries without allowlisted table references", () => {
  const result = isSqlAllowed("SELECT 1");
  assert.equal(result.allowed, false);
  assert.match(result.reason ?? "", /allowlisted analytics tables/i);
});

test("blocks side-effect function calls even when wrapped in SELECT", () => {
  const result = isSqlAllowed("SELECT setval('orders_id_seq', 1, false)");
  assert.equal(result.allowed, false);
  assert.match(result.reason ?? "", /forbidden function/i);
});

test("blocks resource abuse functions", () => {
  const result = isSqlAllowed("SELECT pg_sleep(5)");
  assert.equal(result.allowed, false);
  assert.match(result.reason ?? "", /forbidden function/i);
});
