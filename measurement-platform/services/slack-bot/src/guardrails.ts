/**
 * guardrails.ts — Enforce SELECT only and allowlisted tables on generated SQL.
 */

const ALLOWLISTED_TABLES = new Set([
  "fact_spend_daily",
  "fact_kpi_daily",
  "fact_kpi_geo_daily",
  "fact_klaviyo_daily",
  "fact_tiktok_organic_daily",
  "fact_spend_daily_fx",
  "fact_customers_daily",
  "dim_campaign",
  "dim_customers",
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
  "public_marts.fact_spend_daily_fx",
  "public_marts.fact_customers_daily",
  "public_marts.dim_campaign",
  "public_marts.dim_customers",
  "public_marts.dim_geo",
  // public schema (experiments)
  "public.experiments",
  "public.experiment_results",
  "public.marketing_events",
  "public.data_quality_flags",
  "public.pipeline_runs",
  // raw schema (Airbyte source tables — read-only analytics)
  "meta_ads_insights",
  "meta_customaccount_insights_daily",
  "google_account_performance_report",
  "account_performance_report",
  "tiktok_advertisers_reports_daily",
  "orders",
  "klaviyo_campaigns",
  "raw.meta_ads_insights",
  "raw.meta_customaccount_insights_daily",
  "raw.google_account_performance_report",
  "raw.account_performance_report",
  "raw.tiktok_advertisers_reports_daily",
  "raw.orders",
  "raw.klaviyo_campaigns",
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
 * Returns true if the SQL is allowed (SELECT/WITH only, allowlisted tables).
 */
export function isSqlAllowed(sql: string): { allowed: boolean; reason?: string } {
  // Strip leading SQL comments before checking the first keyword, then lowercase.
  const normalized = sql
    .replace(/^(\s*--[^\n]*\n)+/g, "")
    .replace(/^(\s*\/\*[\s\S]*?\*\/\s*)+/g, "")
    .trim()
    .toLowerCase();
  // Allow read-only entry points: SELECT and WITH (CTE).
  // FORBIDDEN_PATTERNS below still catches any embedded INSERT/UPDATE/etc.
  if (!/^select\b/.test(normalized) && !/^with\b/.test(normalized)) {
    return { allowed: false, reason: "Only SELECT or WITH (CTE) queries are allowed" };
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
