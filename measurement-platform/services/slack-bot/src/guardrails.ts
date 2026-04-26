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
 * Returns true if the SQL is allowed (SELECT only, allowlisted tables).
 */
export function isSqlAllowed(sql: string): { allowed: boolean; reason?: string } {
  const normalized = sql.trim().toLowerCase();
  if (!normalized.startsWith("select ")) {
    return { allowed: false, reason: "Only SELECT queries are allowed" };
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
