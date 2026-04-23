/**
 * guardrails.ts — Enforce SELECT only and allowlisted tables on generated SQL.
 */

const ALLOWLISTED_TABLES = new Set([
  "fact_spend_daily",
  "fact_kpi_daily",
  "fact_kpi_geo_daily",
  "fact_klaviyo_daily",
  "fact_tiktok_organic_daily",
  "fact_tiktok_gmv_daily",
  "fact_tiktok_gmv_max_daily",
  "dim_campaign",
  "dim_geo",
  "marketing_events",
  "experiments",
  "experiment_results",
  "data_quality_flags",
  "pipeline_runs",
  // public schema tables
  "public.marketing_events",
  "public.experiments",
  "public.experiment_results",
  "public.data_quality_flags",
  "public.pipeline_runs",
  // public_marts schema (dbt output)
  "public_marts.fact_spend_daily",
  "public_marts.fact_kpi_daily",
  "public_marts.fact_kpi_geo_daily",
  "public_marts.fact_klaviyo_daily",
  "public_marts.fact_tiktok_organic_daily",
  "public_marts.fact_tiktok_gmv_daily",
  "public_marts.fact_tiktok_gmv_max_daily",
  "public_marts.dim_campaign",
  "public_marts.dim_geo",
]);

const FORBIDDEN_PATTERNS = [
  /;\s*(\s*insert|update|delete|drop|create|alter|truncate|grant|revoke)/i,
  /(\binsert\b|\bupdate\b|\bdelete\b|\bdrop\b|\bcreate\b|\balter\b|\btruncate\b|\bgrant\b|\brevoke\b)/i,
];

function normalizeIdentifier(identifier: string): string {
  const cleaned = identifier.trim().replace(/[),;]+$/g, "");
  const parts = cleaned
    .split(".")
    .map((part) => part.trim().replace(/^"(.+)"$/, "$1"))
    .filter(Boolean);

  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].toLowerCase();

  const table = parts[parts.length - 1].toLowerCase();
  const schema = parts[parts.length - 2].toLowerCase();
  return `${schema}.${table}`;
}

/**
 * Returns true if the SQL is allowed (SELECT only, allowlisted tables).
 */
export function isSqlAllowed(sql: string): { allowed: boolean; reason?: string } {
  const normalized = sql.trim().toLowerCase();
  if (!normalized.startsWith("select ")) {
    return { allowed: false, reason: "Only SELECT queries are allowed" };
  }
  for (const re of FORBIDDEN_PATTERNS) {
    if (re.test(sql)) {
      return { allowed: false, reason: "Query contains forbidden statement" };
    }
  }
  // Extract table names from FROM and JOIN (simple heuristic)
  const fromMatch = sql.match(/\bfrom\s+([\w."]+)/gi);
  const joinMatch = sql.match(/\bjoin\s+([\w."]+)/gi);
  const tables = [...(fromMatch || []), ...(joinMatch || [])].map((s) =>
    normalizeIdentifier(s.replace(/\b(from|join)\s+/i, "").trim())
  );
  for (const t of tables) {
    if (!t) {
      return { allowed: false, reason: "Could not parse table reference" };
    }
    if (t.includes(".")) {
      // For schema-qualified names, require an exact schema.table allowlist match.
      if (!ALLOWLISTED_TABLES.has(t)) {
        return { allowed: false, reason: `Table not allowlisted: ${t}` };
      }
      continue;
    }
    if (!ALLOWLISTED_TABLES.has(t)) {
      return { allowed: false, reason: `Table not allowlisted: ${t}` };
    }
  }
  return { allowed: true };
}

/**
 * Extract table names from SQL for audit (simple).
 */
export function extractTablesUsed(sql: string): string | null {
  const fromMatch = sql.match(/\bfrom\s+([\w."]+)/gi);
  const joinMatch = sql.match(/\bjoin\s+([\w."]+)/gi);
  const tables = [...(fromMatch || []), ...(joinMatch || [])].map((s) =>
    normalizeIdentifier(s.replace(/\b(from|join)\s+/i, "").trim())
  );
  return tables.length ? tables.join(", ") : null;
}
