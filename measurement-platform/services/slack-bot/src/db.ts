/**
 * db.ts — Dynamic Supabase + Postgres connections, routed by clientSlug.
 * Falls back to legacy env vars when no clientSlug is provided.
 */

import { createClient, SupabaseClient } from "@supabase/supabase-js";
import { Pool } from "pg";
import { getClient } from "./client_registry";

// Per-client caches
const supabaseClients: Map<string, SupabaseClient> = new Map();
const pgPools: Map<string, Pool> = new Map();

/** Get (or create) a Supabase client for the given client slug. */
export function getSupabase(clientSlug?: string): SupabaseClient | null {
  const key = clientSlug || "__default__";

  const cached = supabaseClients.get(key);
  if (cached) return cached;

  let url: string | undefined;
  let serviceKey: string | undefined;

  if (clientSlug) {
    const config = getClient(clientSlug);
    if (config) {
      url = config.supabaseUrl;
      serviceKey = config.supabaseServiceKey;
    }
  }

  // Fallback to env vars
  if (!url || !serviceKey) {
    url = process.env.SUPABASE_URL;
    serviceKey = process.env.SUPABASE_SERVICE_KEY;
  }

  if (!url || !serviceKey) return null;

  const client = createClient(url, serviceKey);
  supabaseClients.set(key, client);
  return client;
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

export async function logQueryAudit(row: AuditRow, clientSlug?: string): Promise<void> {
  const supabase = getSupabase(clientSlug);
  if (!supabase) return;
  await supabase.from("ai_query_audit").insert({
    user_id: row.user_id ?? null,
    channel_id: row.channel_id ?? null,
    client_slug: row.client_slug ?? null,
    prompt: row.prompt ?? null,
    sql_executed: row.sql_executed ?? null,
    table_used: row.table_used ?? null,
    row_count: row.row_count ?? null,
    error_message: row.error_message ?? null,
    metadata: row.metadata ?? null,
  });
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

  // Fallback to env var
  if (!dbUrl) dbUrl = process.env.SUPABASE_DB_URL;
  if (!dbUrl) return null;

  const pool = new Pool({
    connectionString: dbUrl,
    ssl: { rejectUnauthorized: false },
    max: 3,
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
