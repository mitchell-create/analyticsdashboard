/**
 * db.ts — Postgres connections routed by clientSlug.
 * Reads only — uses pg.Pool. Writes use parameterised pg.Pool.query.
 */

import { Pool } from "pg";
import { getClient } from "./client_registry";

const pgPools: Map<string, Pool> = new Map();

function shouldUseSsl(dbUrl: string): boolean {
  try {
    const parsed = new URL(dbUrl);
    const host = parsed.hostname.toLowerCase();
    const sslMode = parsed.searchParams.get("sslmode")?.toLowerCase();

    if (sslMode === "disable") return false;
    if (sslMode === "require") return true;
    if (host === "localhost" || host === "127.0.0.1" || host === "::1") return false;
    if (host.startsWith("100.")) return false;

    return true;
  } catch {
    return true;
  }
}

export interface AuditRow {
  user_id?: string;
  channel_id?: string;
  client_slug?: string;
  prompt?: string;
  sql_executed?: string | null;
  table_used?: string;
  row_count?: number;
  error_message?: string;
  metadata?: Record<string, unknown>;
}

/** Get (or create) a Postgres Pool for the given client slug. */
function getPool(clientSlug?: string): Pool | null {
  const key = clientSlug || "__default__";

  const cached = pgPools.get(key);
  if (cached) return cached;

  let dbUrl: string | undefined;

  if (clientSlug) {
    const config = getClient(clientSlug);
    if (config) dbUrl = config.dbUrl;
  }

  if (!dbUrl) dbUrl = process.env.SUPABASE_DB_URL;
  if (!dbUrl) return null;

  const pool = new Pool({
    connectionString: dbUrl,
    ssl: shouldUseSsl(dbUrl) ? { rejectUnauthorized: false } : false,
    max: 3,
    connectionTimeoutMillis: 15000,
    idleTimeoutMillis: 30000,
  });
  pgPools.set(key, pool);
  return pool;
}

/** Run a single SELECT query via Postgres Pool for the given client. */
export async function runReadOnlyQuery(
  sql: string,
  clientSlug?: string
): Promise<{ data: unknown[]; error: Error | null }> {
  const pool = getPool(clientSlug);
  if (!pool) return { data: [], error: new Error("No database connection configured") };
  try {
    const res = await pool.query(sql);
    return { data: res.rows as unknown[], error: null };
  } catch (e) {
    return { data: [], error: e instanceof Error ? e : new Error(String(e)) };
  }
}

/** Run a parameterised write query (INSERT/UPDATE/DELETE). Returns rows from RETURNING clause if any. */
export async function runWriteQuery(
  sql: string,
  params: unknown[] = [],
  clientSlug?: string
): Promise<{ rows: unknown[]; error: Error | null }> {
  const pool = getPool(clientSlug);
  if (!pool) return { rows: [], error: new Error("No database connection configured") };
  try {
    const res = await pool.query(sql, params);
    return { rows: res.rows as unknown[], error: null };
  } catch (e) {
    return { rows: [], error: e instanceof Error ? e : new Error(String(e)) };
  }
}

export async function logQueryAudit(row: AuditRow, clientSlug?: string): Promise<void> {
  const sql = `
    INSERT INTO public.ai_query_audit
      (user_id, channel_id, client_slug, prompt, sql_executed, table_used, row_count, error_message, metadata)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
  `;
  const params = [
    row.user_id ?? null,
    row.channel_id ?? null,
    row.client_slug ?? null,
    row.prompt ?? null,
    row.sql_executed ?? null,
    row.table_used ?? null,
    row.row_count ?? null,
    row.error_message ?? null,
    row.metadata ? JSON.stringify(row.metadata) : null,
  ];
  await runWriteQuery(sql, params, clientSlug);
}
