import { extractTablesUsed, isSqlAllowed } from "./guardrails";

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function run(): void {
  const allowPublicMarts = isSqlAllowed("SELECT * FROM public_marts.fact_spend_daily LIMIT 1");
  assert(allowPublicMarts.allowed, "Expected public_marts table to be allowed");

  const allowUnqualified = isSqlAllowed("SELECT * FROM fact_spend_daily LIMIT 1");
  assert(allowUnqualified.allowed, "Expected allowlisted unqualified table to be allowed");

  const blockCrossSchema = isSqlAllowed("SELECT * FROM secrets.fact_kpi_daily LIMIT 1");
  assert(!blockCrossSchema.allowed, "Expected non-allowlisted schema-qualified table to be blocked");

  const blockQuotedCrossSchema = isSqlAllowed('SELECT * FROM "Secrets"."fact_kpi_daily" LIMIT 1');
  assert(!blockQuotedCrossSchema.allowed, "Expected quoted non-allowlisted schema-qualified table to be blocked");

  const allowPublicSchema = isSqlAllowed("SELECT * FROM public.experiments LIMIT 1");
  assert(allowPublicSchema.allowed, "Expected explicitly allowlisted public schema table to be allowed");

  const tablesUsed = extractTablesUsed('SELECT * FROM "Public_Marts"."fact_spend_daily"');
  assert(tablesUsed === "public_marts.fact_spend_daily", "Expected normalized table extraction");
}

run();
console.log("guardrails tests passed");
