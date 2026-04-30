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
  /\btable\s+[\w."]+/i,
  /\b(pg_sleep|pg_read_file|pg_read_binary_file|pg_ls_dir|pg_stat_file|pg_terminate_backend|pg_cancel_backend|dblink)\s*\(/i,
];

const CLAUSE_BOUNDARY =
  /\b(where|group\s+by|order\s+by|having|limit|offset|union|intersect|except|returning)\b/i;

function splitTopLevelCommaList(segment: string): string[] {
  const parts: string[] = [];
  let current = "";
  let depth = 0;
  let quote: '"' | "'" | null = null;

  for (let i = 0; i < segment.length; i += 1) {
    const ch = segment[i];
    const next = segment[i + 1];

    if (quote) {
      current += ch;
      if (ch === quote && next === quote) {
        current += next;
        i += 1;
      } else if (ch === quote) {
        quote = null;
      }
      continue;
    }

    if (ch === '"' || ch === "'") {
      quote = ch;
      current += ch;
    } else if (ch === "(") {
      depth += 1;
      current += ch;
    } else if (ch === ")") {
      depth = Math.max(0, depth - 1);
      current += ch;
    } else if (ch === "," && depth === 0) {
      parts.push(current);
      current = "";
    } else {
      current += ch;
    }
  }

  if (current.trim()) parts.push(current);
  return parts;
}

function firstRelationToken(part: string): string | null {
  const trimmed = part.trim();
  if (!trimmed || trimmed.startsWith("(")) return null;

  const match = trimmed.match(/^((?:"[^"]+"|\w+)(?:\.(?:"[^"]+"|\w+))?)/);
  if (!match) return null;
  return match[1].replace(/"/g, "");
}

function extractRelationNames(sql: string): string[] {
  const relations: string[] = [];
  const relationStart = /\b(from|join)\b/gi;
  let match: RegExpExecArray | null;

  while ((match = relationStart.exec(sql)) !== null) {
    const keyword = match[1].toLowerCase();
    const segmentStart = relationStart.lastIndex;
    const rest = sql.slice(segmentStart);
    const boundary = rest.search(keyword === "from" ? CLAUSE_BOUNDARY : /\b(on|using|where|group\s+by|order\s+by|having|limit|offset|union|intersect|except)\b/i);
    const segment = boundary >= 0 ? rest.slice(0, boundary) : rest;

    for (const part of splitTopLevelCommaList(segment)) {
      const relation = firstRelationToken(part);
      if (relation) relations.push(relation);
    }
  }

  return relations;
}

function hasMultipleStatements(sql: string): boolean {
  const statements = sql
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean);
  return statements.length > 1;
}

/**
 * Returns true if the SQL is allowed (SELECT only, allowlisted tables).
 */
export function isSqlAllowed(sql: string): { allowed: boolean; reason?: string } {
  const normalized = sql.trim().toLowerCase();
  if (!normalized.startsWith("select ")) {
    return { allowed: false, reason: "Only SELECT queries are allowed" };
  }
  if (hasMultipleStatements(sql)) {
    return { allowed: false, reason: "Multiple SQL statements are not allowed" };
  }
  for (const re of FORBIDDEN_PATTERNS) {
    if (re.test(sql)) {
      return { allowed: false, reason: "Query contains forbidden statement" };
    }
  }
  const tables = extractRelationNames(sql);
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
  const tables = extractRelationNames(sql);
  return tables.length ? tables.join(", ") : null;
}
