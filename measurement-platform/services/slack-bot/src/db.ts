/**
 * db.ts — Supabase client for Slack bot (read-only queries; audit log to ai_query_audit).
 * Uses SUPABASE_URL + SUPABASE_SERVICE_KEY for audit; SUPABASE_DB_URL (postgres) for running SELECT.
 */

import { createClient, SupabaseClient } from "@supabase/supabase-js";
import { Client as PgClient } from "pg";

let supabaseClient: SupabaseClient | null = null;
const READ_ONLY_QUERY_TIMEOUT_MS = 15_000;

export function getSupabase(): SupabaseClient | null {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) return null;
  if (!supabaseClient) supabaseClient = createClient(url, key);
  return supabaseClient;
}

export interface AuditRow {
  user_id?: string;
  channel_id?: string;
  prompt?: string;
  sql_executed?: string | null;
  table_used?: string;
  row_count?: number;
  error_message?: string;
  metadata?: Record<string, unknown>;
}

export async function logQueryAudit(row: AuditRow): Promise<void> {
  const supabase = getSupabase();
  if (!supabase) return;
  await supabase.from("ai_query_audit").insert({
    user_id: row.user_id ?? null,
    channel_id: row.channel_id ?? null,
    prompt: row.prompt ?? null,
    sql_executed: row.sql_executed ?? null,
    table_used: row.table_used ?? null,
    row_count: row.row_count ?? null,
    error_message: row.error_message ?? null,
    metadata: row.metadata ?? null,
  });
}

/** Run a single SELECT query via Postgres. Use SUPABASE_DB_URL (postgres://...). */
export async function runReadOnlyQuery(
  sql: string
): Promise<{ data: unknown[]; error: Error | null }> {
  const dbUrl = process.env.SUPABASE_DB_URL;
  if (!dbUrl) return { data: [], error: new Error("SUPABASE_DB_URL not set") };
  const pg = new PgClient({
    connectionString: dbUrl,
    ssl: { rejectUnauthorized: false },
  });
  try {
    await pg.connect();
    await pg.query(`SET statement_timeout = ${READ_ONLY_QUERY_TIMEOUT_MS}`);
    const res = await pg.query(sql);
    return { data: res.rows as unknown[], error: null };
  } catch (e) {
    return { data: [], error: e instanceof Error ? e : new Error(String(e)) };
  } finally {
    await pg.end();
  }
}
