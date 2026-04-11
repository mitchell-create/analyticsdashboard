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

function normalizeTableToken(rawToken: string): string | null {
  let token = rawToken.trim();
  if (!token) return null;

  // Skip subqueries or function calls in FROM/JOIN clauses.
  if (token.startsWith("(")) return null;

  if (token.toLowerCase().startsWith("lateral ")) {
    token = token.slice("lateral ".length).trim();
  }
  if (token.toLowerCase().startsWith("only ")) {
    token = token.slice("only ".length).trim();
  }
  if (token.startsWith("(")) return null;

  const first = token.split(/\s+/)[0]?.replace(/,+$/, "");
  if (!first) return null;

  // Remove identifier quotes and alias punctuation.
  const normalized = first.replace(/"/g, "").trim();
  if (!normalized || normalized.includes("(")) return null;
  return normalized;
}

function extractTables(sql: string): string[] {
  const tables: string[] = [];
  const clauseRegex =
    /\b(from|join)\s+([\s\S]*?)(?=\b(where|group\s+by|order\s+by|limit|offset|union|having|join|on)\b|$)/gi;

  let match: RegExpExecArray | null;
  while ((match = clauseRegex.exec(sql)) !== null) {
    const clauseBody = match[2];
    for (const chunk of clauseBody.split(",")) {
      const table = normalizeTableToken(chunk);
      if (table) tables.push(table);
    }
  }

  return tables;
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

  const tables = extractTables(sql);
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
  const tables = extractTables(sql);
  return tables.length ? tables.join(", ") : null;
}
