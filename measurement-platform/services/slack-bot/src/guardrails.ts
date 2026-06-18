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

// Block known side-effect / resource-abuse functions that can still be invoked from SELECT.
const FORBIDDEN_FUNCTION_PATTERNS = [
  /\bsetval\s*\(/i,
  /\bnextval\s*\(/i,
  /\bcurrval\s*\(/i,
  /\bpg_sleep\s*\(/i,
  /\bpg_terminate_backend\s*\(/i,
  /\bpg_cancel_backend\s*\(/i,
];

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
  for (const re of FORBIDDEN_FUNCTION_PATTERNS) {
    if (re.test(sql)) {
      return { allowed: false, reason: "Query contains forbidden function" };
    }
  }
  // Extract table names from FROM and JOIN (simple heuristic)
  const fromMatch = sql.match(/\bfrom\s+([\w."]+)/gi);
  const joinMatch = sql.match(/\bjoin\s+([\w."]+)/gi);
  const tables = [...(fromMatch || []), ...(joinMatch || [])].map((s) =>
    s.replace(/\b(from|join)\s+/i, "").trim().replace(/^["']?([^."']+)/, "$1")
  );
  if (tables.length === 0) {
    return {
      allowed: false,
      reason: "Query must reference allowlisted analytics tables",
    };
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
  const fromMatch = sql.match(/\bfrom\s+([\w."]+)/gi);
  const joinMatch = sql.match(/\bjoin\s+([\w."]+)/gi);
  const tables = [...(fromMatch || []), ...(joinMatch || [])].map((s) =>
    s.replace(/\b(from|join)\s+/i, "").trim()
  );
  return tables.length ? tables.join(", ") : null;
}
