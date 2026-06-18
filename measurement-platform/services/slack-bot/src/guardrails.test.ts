import assert from "node:assert/strict";
import { isSqlAllowed } from "./guardrails";

function run(): void {
  const allowed = isSqlAllowed(
    "SELECT report_date, revenue FROM public_marts.fact_kpi_daily ORDER BY report_date DESC LIMIT 30"
  );
  assert.equal(allowed.allowed, true, "Expected allowlisted SELECT query to pass");

  const blockedNoTable = isSqlAllowed("SELECT 1");
  assert.equal(blockedNoTable.allowed, false, "Expected table-less SELECT to be blocked");
  assert.match(
    blockedNoTable.reason ?? "",
    /must reference allowlisted tables/i,
    "Expected table reference failure reason"
  );

  const blockedDynamicExec = isSqlAllowed(
    "SELECT query_to_xml('select version()', true, false, '')"
  );
  assert.equal(
    blockedDynamicExec.allowed,
    false,
    "Expected query_to_xml dynamic SQL path to be blocked"
  );
  assert.match(
    blockedDynamicExec.reason ?? "",
    /Forbidden function call: query_to_xml/i,
    "Expected forbidden function reason"
  );
}

run();
console.log("guardrails tests passed");
