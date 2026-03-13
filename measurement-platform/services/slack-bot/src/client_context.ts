/**
 * client_context.ts — Extracts client context from user input and manages defaults.
 */

import { getClient, listClientSlugs, listClients, matchClients } from "./client_registry";

export interface ClientContext {
  clientSlug: string;
  displayName: string;
}

/**
 * Parse client from command text.
 * 1. Checks for explicit --client <slug> flag (strips it from text).
 * 2. Falls back to NL match against registered client names.
 * Returns { client, cleanedText } or null if no client detected.
 */
export function parseClientFromText(
  text: string
): { client: ClientContext; cleanedText: string } | null {
  // 1. Explicit --client flag
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
    // Flag present but invalid slug — return null so caller can show error
    return null;
  }

  // 2. NL match against client names
  const matches = matchClients(text);
  if (matches.length === 1) {
    return {
      client: {
        clientSlug: matches[0].slug,
        displayName: matches[0].displayName,
      },
      cleanedText: text, // keep original text — LLM handles the name fine
    };
  }

  return null;
}

// In-memory defaults (reset on restart). Channel defaults take priority.
const channelDefaults: Map<string, string> = new Map();
const userDefaults: Map<string, string> = new Map();

/** Get default client for a channel or user. Channel takes priority. */
export function getDefaultClient(
  channelId?: string,
  userId?: string
): ClientContext | undefined {
  const slug =
    (channelId ? channelDefaults.get(channelId) : undefined) ??
    (userId ? userDefaults.get(userId) : undefined);
  if (!slug) return undefined;
  const config = getClient(slug);
  if (!config) return undefined;
  return { clientSlug: config.slug, displayName: config.displayName };
}

/** Set default client for a channel or user. Returns false if slug is invalid. */
export function setDefaultClient(
  scope: "channel" | "user",
  scopeId: string,
  slug: string
): boolean {
  const config = getClient(slug);
  if (!config) return false;
  if (scope === "channel") {
    channelDefaults.set(scopeId, config.slug);
  } else {
    userDefaults.set(scopeId, config.slug);
  }
  return true;
}

/**
 * Full resolution pipeline. Tries in order:
 * 1. Explicit --client flag or NL match
 * 2. Channel/user default
 * 3. Single-client registry (auto-select)
 * Returns { client, cleanedText } or null if ambiguous.
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

  // Check if --client flag was used but with invalid slug
  if (/--client\s+\S+/i.test(text)) {
    return { client: null, cleanedText: text.replace(/--client\s+\S+/i, "").trim(), ambiguous: true };
  }

  // 2. Channel/user default
  const defaultClient = getDefaultClient(channelId, userId);
  if (defaultClient) {
    return { client: defaultClient, cleanedText: text, ambiguous: false };
  }

  // 3. Single-client auto-select
  const slugs = listClientSlugs();
  if (slugs.length === 1) {
    const config = listClients()[0];
    return {
      client: { clientSlug: config.slug, displayName: config.displayName },
      cleanedText: text,
      ambiguous: false,
    };
  }

  // Multiple clients, no way to resolve
  return { client: null, cleanedText: text, ambiguous: slugs.length > 1 };
}
