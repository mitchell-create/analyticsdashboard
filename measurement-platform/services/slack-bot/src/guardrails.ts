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

const DANGEROUS_FUNCTION_PATTERNS = [
  /\bpg_sleep\s*\(/i,
  /\bpg_(terminate|cancel)_backend\s*\(/i,
  /\bpg_read_file\s*\(/i,
  /\bpg_ls_(dir|wal|archive_statusdir)\s*\(/i,
  /\bdblink(_exec)?\s*\(/i,
];

function trimOptionalTrailingSemicolon(sql: string): string {
  return sql.trim().replace(/;\s*$/, "");
}

function extractReferencedTables(sql: string): string[] {
  const fromMatch = sql.match(/\bfrom\s+([\w."]+)/gi);
  const joinMatch = sql.match(/\bjoin\s+([\w."]+)/gi);
  return [...(fromMatch || []), ...(joinMatch || [])].map((s) =>
    s
      .replace(/\b(from|join)\s+/i, "")
      .trim()
      .replace(/"/g, "")
      .toLowerCase()
  );
}

/**
 * Returns true if the SQL is allowed (SELECT only, allowlisted tables).
 */
export function isSqlAllowed(sql: string): { allowed: boolean; reason?: string } {
  const normalized = trimOptionalTrailingSemicolon(sql).toLowerCase();
  if (!normalized.startsWith("select ")) {
    return { allowed: false, reason: "Only SELECT queries are allowed" };
  }

  if (normalized.includes(";")) {
    return { allowed: false, reason: "Multiple SQL statements are not allowed" };
  }

  for (const re of FORBIDDEN_PATTERNS) {
    if (re.test(sql)) {
      return { allowed: false, reason: "Query contains forbidden statement" };
    }
  }

  for (const re of DANGEROUS_FUNCTION_PATTERNS) {
    if (re.test(sql)) {
      return { allowed: false, reason: "Query contains dangerous database function" };
    }
  }

  // Extract table names from FROM and JOIN (simple heuristic).
  const tables = extractReferencedTables(sql);
  if (tables.length === 0) {
    return { allowed: false, reason: "Query must reference an allowlisted table" };
  }

  for (const t of tables) {
    const base = t.split(".").pop() ?? t;
    if (!ALLOWLISTED_TABLES.has(base) && !ALLOWLISTED_TABLES.has(t)) {
      return { allowed: false, reason: `Table not allowlisted: ${t}` };
    }
  }
  return { allowed: true };
}

/**
 * Extract table names from SQL for audit (simple).
 */
export function extractTablesUsed(sql: string): string | null {
  const tables = extractReferencedTables(sql);
  return tables.length ? tables.join(", ") : null;
}
