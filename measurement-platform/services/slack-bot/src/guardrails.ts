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
  /\b(pg_sleep|pg_read_file|pg_read_binary_file|pg_ls_dir|dblink|lo_import|lo_export|copy)\s*\(/i,
];

const CLAUSE_BOUNDARY =
  /\b(join|on|where|group\s+by|order\s+by|having|limit|offset|union|intersect|except|qualify)\b/i;

function splitTopLevelCommaList(segment: string): string[] {
  const parts: string[] = [];
  let current = "";
  let depth = 0;
  let quote: string | null = null;

  for (let i = 0; i < segment.length; i += 1) {
    const char = segment[i];
    const next = segment[i + 1];

    if (quote) {
      current += char;
      if (char === quote) {
        if ((quote === "'" || quote === '"') && next === quote) {
          current += next;
          i += 1;
        } else {
          quote = null;
        }
      }
      continue;
    }

    if (char === "'" || char === '"' || char === "`") {
      quote = char;
      current += char;
      continue;
    }

    if (char === "(") depth += 1;
    if (char === ")" && depth > 0) depth -= 1;

    if (char === "," && depth === 0) {
      parts.push(current.trim());
      current = "";
      continue;
    }

    current += char;
  }

  if (current.trim()) parts.push(current.trim());
  return parts;
}

function normalizeTableName(identifier: string): string {
  return identifier
    .split(".")
    .map((part) => part.trim().replace(/^["'`]|["'`]$/g, ""))
    .join(".");
}

function extractTableNames(sql: string): string[] {
  const tables = new Set<string>();
  const relationStart = /\b(from|join)\s+/gi;
  let match: RegExpExecArray | null;

  while ((match = relationStart.exec(sql)) !== null) {
    const remainder = sql.slice(relationStart.lastIndex);
    const boundary = remainder.search(CLAUSE_BOUNDARY);
    const segment = (boundary === -1 ? remainder : remainder.slice(0, boundary)).trim();

    for (const relation of splitTopLevelCommaList(segment)) {
      const token = relation.match(/^([\w."]+)/)?.[1];
      if (token) {
        tables.add(normalizeTableName(token));
      }
    }
  }

  return [...tables];
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
  const withoutTrailingSemicolon = sql.trim().replace(/;+\s*$/, "");
  if (withoutTrailingSemicolon.includes(";")) {
    return { allowed: false, reason: "Multiple SQL statements are not allowed" };
  }
  for (const re of FORBIDDEN_PATTERNS) {
    if (re.test(sql)) {
      return { allowed: false, reason: "Query contains forbidden statement" };
    }
  }
  const tables = extractTableNames(sql);
  if (!tables.length) {
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
  const tables = extractTableNames(sql);
  return tables.length ? tables.join(", ") : null;
}
