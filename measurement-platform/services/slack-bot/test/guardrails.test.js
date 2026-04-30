const assert = require("node:assert/strict");
const { isSqlAllowed, extractTablesUsed } = require("../dist/guardrails");

function assertAllowed(sql) {
  const result = isSqlAllowed(sql);
  assert.equal(result.allowed, true, result.reason);
}

function assertBlocked(sql, reasonFragment) {
  const result = isSqlAllowed(sql);
  assert.equal(result.allowed, false, `${sql} should have been blocked`);
  assert.match(result.reason || "", reasonFragment);
}

assertAllowed("SELECT spend FROM public_marts.fact_spend_daily LIMIT 10");
assertAllowed(
  "SELECT * FROM public_marts.fact_spend_daily s, public_marts.fact_kpi_daily k WHERE s.report_date = k.report_date"
);

assertBlocked(
  "SELECT * FROM public_marts.fact_spend_daily; TABLE pg_user;",
  /Multiple SQL statements/
);
assertBlocked(
  "SELECT * FROM public_marts.fact_spend_daily WHERE EXISTS (TABLE pg_user)",
  /forbidden/
);
assertBlocked(
  "SELECT * FROM public_marts.fact_spend_daily, private.customer_emails LIMIT 10",
  /Table not allowlisted: private.customer_emails/
);
assertBlocked("SELECT pg_sleep(10)", /forbidden/);
assertBlocked("SELECT 1", /allowlisted table/);

assert.equal(
  extractTablesUsed(
    "SELECT * FROM public_marts.fact_spend_daily s, public_marts.fact_kpi_daily k WHERE s.report_date = k.report_date"
  ),
  "public_marts.fact_spend_daily, public_marts.fact_kpi_daily"
);

console.log("guardrails tests passed");
