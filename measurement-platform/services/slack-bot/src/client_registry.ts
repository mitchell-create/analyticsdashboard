/**
 * client_registry.ts — Multi-client config: loads client → DB mappings from clients.json.
 * Falls back to single-client mode using legacy SUPABASE_* env vars when no registry exists.
 */

import * as fs from "fs";
import * as path from "path";

export interface ClientConfig {
  slug: string;
  displayName: string;
  supabaseUrl: string;
  supabaseServiceKey: string;
  dbUrl: string;
}

const clients: Map<string, ClientConfig> = new Map();

/** Load client registry from CLIENTS_JSON env var, JSON file, or fall back to single-client mode. */
export function loadClientRegistry(): void {
  clients.clear();

  // Priority 1: CLIENTS_JSON env var (for Docker/Railway where file isn't in git)
  const envJson = process.env.CLIENTS_JSON;
  if (envJson) {
    try {
      const entries: ClientConfig[] = JSON.parse(envJson);
      for (const entry of entries) {
        if (entry.slug && entry.dbUrl) {
          clients.set(entry.slug.toLowerCase(), {
            ...entry,
            slug: entry.slug.toLowerCase(),
          });
        }
      }
      console.log(`  Client registry loaded from CLIENTS_JSON env var (${clients.size} clients)`);
      return;
    } catch (e) {
      console.error("Failed to parse CLIENTS_JSON env var:", e instanceof Error ? e.message : e);
    }
  }

  // Priority 2: JSON file on disk
  const registryPath =
    process.env.CLIENT_REGISTRY_PATH ||
    path.join(process.cwd(), "clients.json");

  if (fs.existsSync(registryPath)) {
    const raw = fs.readFileSync(registryPath, "utf-8");
    const entries: ClientConfig[] = JSON.parse(raw);
    for (const entry of entries) {
      if (entry.slug && entry.dbUrl) {
        clients.set(entry.slug.toLowerCase(), {
          ...entry,
          slug: entry.slug.toLowerCase(),
        });
      }
    }
    console.log(`  Client registry loaded from ${registryPath} (${clients.size} clients)`);
    return;
  }

  // Fallback: single-client mode from legacy env vars
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  const dbUrl = process.env.SUPABASE_DB_URL;
  if (url && key && dbUrl) {
    clients.set("default", {
      slug: "default",
      displayName: "Default",
      supabaseUrl: url,
      supabaseServiceKey: key,
      dbUrl,
    });
    console.log("  Client registry: single-client mode from env vars");
  }
}

/** Get a client config by exact slug (case-insensitive). */
export function getClient(slug: string): ClientConfig | undefined {
  return clients.get(slug.toLowerCase());
}

/** Return all registered slugs. */
export function listClientSlugs(): string[] {
  return Array.from(clients.keys());
}

/** Return all client configs. */
export function listClients(): ClientConfig[] {
  return Array.from(clients.values());
}

/**
 * Fuzzy NL match: find clients whose slug or displayName appears in the text.
 * Skips the "default" client (used for single-client fallback).
 */
export function matchClients(text: string): ClientConfig[] {
  const lower = text.toLowerCase();
  const matches: ClientConfig[] = [];
  for (const c of clients.values()) {
    if (c.slug === "default") continue;
    if (
      lower.includes(c.slug) ||
      lower.includes(c.displayName.toLowerCase())
    ) {
      matches.push(c);
    }
  }
  return matches;
}
