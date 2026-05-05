/**
 * client_context.ts — Extracts client from user input and manages channel/user defaults.
 * Resolution pipeline: --client flag → NL match → channel default → user default → single-client auto → ambiguous.
 */

import { getClient, matchClients, listClients } from "./client_registry";

export interface ClientContext {
  clientSlug: string;
  displayName: string;
}

// In-memory defaults (channel takes priority over user)
const channelDefaults: Map<string, ClientContext> = new Map();
const userDefaults: Map<string, ClientContext> = new Map();

/** Parse --client <slug> flag from text, or try NL match. Returns null if no client found. */
export function parseClientFromText(
  text: string
): { client: ClientContext; cleanedText: string } | null {
  // 1. Explicit flag: --client <slug>
  const flagMatch = text.match(/--client\s+(\S+)/i);
  if (flagMatch) {
    const slug = flagMatch[1].toLowerCase();
    const config = getClient(slug);
    if (config) {
      const cleanedText = text.replace(/--client\s+\S+/i, "").trim();
      return {
        client: { clientSlug: config.slug, displayName: config.displayName },
        cleanedText,
      };
    }
  }

  // 2. NL match: check if a client name appears in the text
  const matches = matchClients(text);
  if (matches.length === 1) {
    return {
      client: {
        clientSlug: matches[0].slug,
        displayName: matches[0].displayName,
      },
      cleanedText: text,
    };
  }

  return null;
}

/** Get channel or user default. Channel takes priority. */
export function getDefaultClient(
  channelId?: string,
  userId?: string
): ClientContext | undefined {
  if (channelId) {
    const chanDefault = channelDefaults.get(channelId);
    if (chanDefault) return chanDefault;
  }
  if (userId) {
    const userDefault = userDefaults.get(userId);
    if (userDefault) return userDefault;
  }
  return undefined;
}

/** Set a default client for a channel or user. Returns true on success. */
export function setDefaultClient(
  scope: "channel" | "user",
  scopeId: string,
  slug: string
): boolean {
  const config = getClient(slug);
  if (!config) return false;
  const ctx: ClientContext = {
    clientSlug: config.slug,
    displayName: config.displayName,
  };
  if (scope === "channel") {
    channelDefaults.set(scopeId, ctx);
  } else {
    userDefaults.set(scopeId, ctx);
  }
  return true;
}

/**
 * Full resolution pipeline:
 * 1. Parse --client flag or NL match from text
 * 2. Fall back to channel/user default
 * 3. Fall back to single-client auto-select if registry has exactly 1 entry
 * 4. If ambiguous → return null (handler should prompt user to specify)
 */
export function resolveClient(
  text: string,
  channelId?: string,
  userId?: string
): { client: ClientContext | null; cleanedText: string; ambiguous: boolean } {
  // 1. Parse from text
  const parsed = parseClientFromText(text);
  if (parsed) {
    return { client: parsed.client, cleanedText: parsed.cleanedText, ambiguous: false };
  }

  // 2. Channel/user default
  const defaultClient = getDefaultClient(channelId, userId);
  if (defaultClient) {
    return { client: defaultClient, cleanedText: text, ambiguous: false };
  }

  // 3. Single-client auto-select
  const allClients = listClients();
  if (allClients.length === 1) {
    const c = allClients[0];
    return {
      client: { clientSlug: c.slug, displayName: c.displayName },
      cleanedText: text,
      ambiguous: false,
    };
  }

  // 4. Multiple clients, none resolved → ambiguous
  if (allClients.length > 1) {
    return { client: null, cleanedText: text, ambiguous: true };
  }

  // No clients at all (shouldn't happen if registry loaded)
  return { client: null, cleanedText: text, ambiguous: false };
}
