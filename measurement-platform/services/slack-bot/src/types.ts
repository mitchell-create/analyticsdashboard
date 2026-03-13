/**
 * types.ts — Shared type definitions for the Slack bot.
 * Extracted here to avoid circular imports between index.ts and agent modules.
 */

export interface ThreadMessage {
  role: "user" | "assistant";
  content: string;
}
