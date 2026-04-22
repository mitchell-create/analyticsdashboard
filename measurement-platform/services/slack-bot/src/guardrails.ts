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

const FROM_CLAUSE_PATTERN =
  /\bfrom\b([\s\S]*?)(?=\bwhere\b|\bgroup\s+by\b|\border\s+by\b|\blimit\b|\bhaving\b|\bunion\b|\bintersect\b|\bexcept\b|\bjoin\b|$)/i;
const JOIN_TABLE_PATTERN = /\b(?:left|right|full|inner|cross)?\s*join\s+([a-zA-Z0-9_."`]+)/gi;

function normalizeTableRef(tableRef: string): string {
  return tableRef
    .trim()
    .replace(/,$/, "")
    .replace(/"/g, "")
    .replace(/`/g, "")
    .toLowerCase();
}

function extractFromTables(sql: string): string[] {
  const match = sql.match(FROM_CLAUSE_PATTERN);
  if (!match?.[1]) return [];

  return match[1]
    .split(/\s*,\s*/)
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => {
      // Keep only the table token and ignore aliases.
      const token = entry.split(/\s+/)[0];
      return token.startsWith("(") ? "" : normalizeTableRef(token);
    })
    .filter(Boolean);
}

function extractJoinTables(sql: string): string[] {
  const refs: string[] = [];
  for (const match of sql.matchAll(JOIN_TABLE_PATTERN)) {
    refs.push(normalizeTableRef(match[1] ?? ""));
  }
  return refs.filter(Boolean);
}

function extractTableRefs(sql: string): string[] {
  return [...extractFromTables(sql), ...extractJoinTables(sql)];
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

  const tables = extractTableRefs(sql);
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
  const tables = extractTableRefs(sql);
  return tables.length ? tables.join(", ") : null;
}
