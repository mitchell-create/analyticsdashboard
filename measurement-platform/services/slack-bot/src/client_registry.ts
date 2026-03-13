/**
 * client_registry.ts — Maps client slugs to Supabase connection details.
 * Loads from a JSON file (CLIENT_REGISTRY_PATH env var) or falls back to
 * building a single "default" entry from legacy SUPABASE_* env vars.
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

/** Load clients from JSON file or fall back to legacy env vars. */
export function loadClientRegistry(): void {
  clients.clear();

  // Try loading from JSON file
  const registryPath =
    process.env.CLIENT_REGISTRY_PATH ||
    path.join(process.cwd(), "clients.json");

  if (fs.existsSync(registryPath)) {
    try {
      const raw = fs.readFileSync(registryPath, "utf-8");
      const entries: ClientConfig[] = JSON.parse(raw);
      for (const entry of entries) {
        if (entry.slug && entry.dbUrl) {
          clients.set(entry.slug.toLowerCase(), entry);
        }
      }
      return;
    } catch (e) {
      console.error(`Failed to load client registry from ${registryPath}:`, e);
    }
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
  }
}

/** Get a client by exact slug (case-insensitive). */
export function getClient(slug: string): ClientConfig | undefined {
  return clients.get(slug.toLowerCase());
}

/** Get all registered client slugs. */
export function listClientSlugs(): string[] {
  return Array.from(clients.keys());
}

/** Get all registered clients. */
export function listClients(): ClientConfig[] {
  return Array.from(clients.values());
}

/**
 * Fuzzy match: find clients whose slug or displayName appears in the text.
 * Returns matching configs. Skips the "default" slug to avoid false positives.
 */
export function matchClients(text: string): ClientConfig[] {
  const lower = text.toLowerCase();
  const matches: ClientConfig[] = [];
  for (const config of clients.values()) {
    if (config.slug === "default") continue;
    if (
      lower.includes(config.slug.toLowerCase()) ||
      lower.includes(config.displayName.toLowerCase())
    ) {
      matches.push(config);
    }
  }
  return matches;
}
