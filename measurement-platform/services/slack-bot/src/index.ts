/**
 * index.ts — Slack Bolt app: Q&A (NL → SQL → answer), GeoLift experiments, multi-client routing.
 * Env: SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, CLIENT_REGISTRY_PATH (or legacy SUPABASE_* vars).
 */

import "dotenv/config";
import { App } from "@slack/bolt";
import { answerQuery } from "./ai_to_sql";
import { handleGeoliftCommand, isExperimentQuery, isAnalysisRequest, answerExperimentQuery, getNewlyCompletedResults } from "./experiment_agent";
import { isDiagnosticReportRequest, generateDiagnosticReport } from "./diagnostic_report";
import { loadClientRegistry, listClientSlugs } from "./client_registry";
import { resolveClient, setDefaultClient } from "./client_context";

// Re-export ThreadMessage from shared types (avoids circular imports)
export type { ThreadMessage } from "./types";
import type { ThreadMessage } from "./types";

const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  signingSecret: process.env.SLACK_SIGNING_SECRET,
  socketMode: true,
  appToken: process.env.SLACK_APP_TOKEN,
});

const MAX_THREAD_MESSAGES = 20; // limit to keep context reasonable

/** Build disambiguation message when client can't be resolved. */
function disambiguationMessage(): string {
  const slugs = listClientSlugs();
  const clientList = slugs.map((s) => `• *${s}*`).join("\n");
  return `Which client did you want the data for?\n\n${clientList}\n\nJust include the client name in your question (e.g. _"What was Expand's spend last week?"_) or set a default for this channel with \`/analytics set-default <name>\`.`;
}

/**
 * Fetch thread conversation history when a message is a thread reply.
 * Returns prior messages (excluding the current one) as {role, content} pairs.
 */
async function fetchThreadContext(
  channelId: string,
  threadTs: string,
  currentTs: string,
  botUserId: string | undefined,
): Promise<ThreadMessage[]> {
  try {
    const result = await app.client.conversations.replies({
      token: process.env.SLACK_BOT_TOKEN,
      channel: channelId,
      ts: threadTs,
      limit: MAX_THREAD_MESSAGES + 5, // fetch a few extra in case we filter some
    });

    if (!result.messages || result.messages.length <= 1) return [];

    const history: ThreadMessage[] = [];
    for (const msg of result.messages) {
      // Skip the current message (we pass that separately as the prompt)
      if (msg.ts === currentTs) continue;
      // Skip messages with subtypes (joins, edits, etc.)
      if ("subtype" in msg && msg.subtype) continue;

      const text = msg.text || "";
      if (!text.trim()) continue;

      const isBot = msg.bot_id || (botUserId && msg.user === botUserId);
      history.push({
        role: isBot ? "assistant" : "user",
        content: text,
      });
    }

    // Keep only the most recent messages to stay within context limits
    return history.slice(-MAX_THREAD_MESSAGES);
  } catch (e) {
    // If we can't fetch thread history, just continue without it
    console.error("Failed to fetch thread context:", e instanceof Error ? e.message : e);
    return [];
  }
}

// Cache the bot user ID (resolved once on first message)
let cachedBotUserId: string | undefined;

// ─── Channel messages ────────────────────────────────────────────────────────

// Channels where the bot should NOT respond to messages (report-only channels)
const REPORT_ONLY_CHANNELS = new Set([
  "C0AEXRYPA9Y", // #chubblegum — automated reports only
]);

app.message(async ({ message, say }) => {
  if (message.subtype) return;
  const text = "text" in message ? (message.text as string) : "";
  if (!text || text.length < 3) return;

  // Ignore messages in report-only channels (bot posts there on schedule, doesn't chat)
  if (REPORT_ONLY_CHANNELS.has(message.channel)) return;

  // Resolve bot user ID for thread context (do this once)
  if (!cachedBotUserId) {
    try {
      const authResult = await app.client.auth.test({ token: process.env.SLACK_BOT_TOKEN });
      cachedBotUserId = authResult.user_id as string;
    } catch { /* ignore */ }
  }

  // Fetch thread context FIRST so we can use it for both client resolution and routing
  const threadTs = "thread_ts" in message ? (message.thread_ts as string) : undefined;
  let threadContext: ThreadMessage[] = [];
  if (threadTs) {
    threadContext = await fetchThreadContext(
      message.channel,
      threadTs,
      message.ts as string,
      cachedBotUserId,
    );
  }

  let { client, cleanedText, ambiguous } = resolveClient(
    text,
    message.channel,
    message.user
  );

  // Thread-aware client resolution: if client can't be resolved from the current
  // message, check thread history for a previously mentioned client.
  if (ambiguous && !client && threadContext.length > 0) {
    for (const msg of threadContext) {
      if (msg.role === "user") {
        const threadResolve = resolveClient(msg.content, message.channel, message.user);
        if (threadResolve.client) {
          client = threadResolve.client;
          ambiguous = false;
          break;
        }
      }
    }
  }

  if (ambiguous && !client) {
    await say({ text: disambiguationMessage(), thread_ts: message.ts });
    return;
  }

  const options = {
    userId: message.user,
    channelId: message.channel,
    clientSlug: client?.clientSlug,
    threadContext,
  };

  // Thread-aware routing: if the current message is a thread reply, check whether
  // the thread started as an experiment conversation so follow-ups stay routed to
  // the experiment agent even when the new message lacks experiment keywords.
  const threadIsExperiment = threadContext.length > 0
    && threadContext.some((m) => isExperimentQuery(m.content));

  const prefix = client && client.clientSlug !== "default"
    ? `_[${client.displayName}]_ `
    : "";

  try {
    let reply: string;

    if (isDiagnosticReportRequest(cleanedText)) {
      reply = await generateDiagnosticReport(cleanedText, {
        ...options,
        clientDisplayName: client?.displayName,
      });
    } else if (isExperimentQuery(cleanedText) || threadIsExperiment) {
      // For analysis requests (running the R model), use async posting so the user
      // gets an immediate acknowledgment and results are posted when ready.
      if (isAnalysisRequest(cleanedText)) {
        const replyTs = message.ts as string;
        const postUpdate = async (text: string) => {
          await app.client.chat.postMessage({
            token: process.env.SLACK_BOT_TOKEN,
            channel: message.channel,
            text: prefix + text,
            thread_ts: replyTs,
          });
        };
        // Fire-and-forget — don't block the message handler
        answerExperimentQuery(cleanedText, { ...options, postUpdate }).catch((e) => {
          const err = e instanceof Error ? e.message : String(e);
          postUpdate(`:x: Analysis error: ${err}`);
        });
        return; // don't call say() — postUpdate handles all responses
      }
      reply = await answerExperimentQuery(cleanedText, options);
    } else {
      const result = await answerQuery(cleanedText, options);
      reply = result.text;
    }

    if (reply) {
      await say({ text: prefix + reply, thread_ts: message.ts });
    }
  } catch (e) {
    const err = e instanceof Error ? e.message : String(e);
    await say({ text: `Error: ${err}`, thread_ts: message.ts });
  }
});

// ─── /geolift slash command ──────────────────────────────────────────────────

app.command("/geolift", async ({ command, ack, say }) => {
  await ack();
  const rawText = command.text?.trim() || "help";

  const { client, cleanedText, ambiguous } = resolveClient(
    rawText,
    command.channel_id,
    command.user_id
  );

  if (ambiguous && !client) {
    await say({ text: disambiguationMessage() });
    return;
  }

  try {
    const reply = await handleGeoliftCommand(cleanedText, {
      userId: command.user_id,
      channelId: command.channel_id,
      clientSlug: client?.clientSlug,
    });
    const prefix = client && client.clientSlug !== "default"
      ? `_[${client.displayName}]_ `
      : "";
    await say({ text: prefix + reply });
  } catch (e) {
    const err = e instanceof Error ? e.message : String(e);
    await say({ text: `Error: ${err}` });
  }
});

// ─── /analytics slash command ────────────────────────────────────────────────

app.command("/analytics", async ({ command, ack, say }) => {
  await ack();
  const rawText = command.text?.trim() || "Show recent spend by channel";

  // Sub-command: set-default <slug>
  if (rawText.startsWith("set-default ")) {
    const slug = rawText.replace("set-default ", "").trim();
    const success = setDefaultClient("channel", command.channel_id, slug);
    await say({
      text: success
        ? `Default client for this channel set to *${slug}*.`
        : `Unknown client \`${slug}\`. Available: ${listClientSlugs().join(", ")}`,
    });
    return;
  }

  const { client, cleanedText, ambiguous } = resolveClient(
    rawText,
    command.channel_id,
    command.user_id
  );

  if (ambiguous && !client) {
    await say({ text: disambiguationMessage() });
    return;
  }

  const cmdOptions = {
    userId: command.user_id,
    channelId: command.channel_id,
    clientSlug: client?.clientSlug,
  };

  try {
    let reply: string;
    if (isDiagnosticReportRequest(cleanedText)) {
      reply = await generateDiagnosticReport(cleanedText, {
        ...cmdOptions,
        clientDisplayName: client?.displayName,
      });
    } else {
      const result = await answerQuery(cleanedText, cmdOptions);
      reply = result.text;
    }
    const prefix = client && client.clientSlug !== "default"
      ? `_[${client.displayName}]_ `
      : "";
    await say({ text: prefix + reply });
  } catch (e) {
    const err = e instanceof Error ? e.message : String(e);
    await say({ text: `Error: ${err}` });
  }
});

// ─── Results polling (check for completed experiments every 5 minutes) ───────

const EXPERIMENT_CHANNEL_ID = process.env.SLACK_EXPERIMENT_CHANNEL_ID;
const POLL_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

async function pollCompletedExperiments(): Promise<void> {
  if (!EXPERIMENT_CHANNEL_ID) return;
  try {
    const completed = await getNewlyCompletedResults();
    for (const { slug, message } of completed) {
      await app.client.chat.postMessage({
        token: process.env.SLACK_BOT_TOKEN,
        channel: EXPERIMENT_CHANNEL_ID,
        text: message,
      });
      console.log(`Posted results for experiment: ${slug}`);
    }
  } catch (e) {
    console.error("Experiment results poll failed:", e);
  }
}

// ─── Start ───────────────────────────────────────────────────────────────────

(async () => {
  loadClientRegistry();
  await app.start();
  const slugs = listClientSlugs();
  console.log(`Slack bot started (Socket Mode — outbound WebSocket to Slack, no port bound)`);
  console.log(`  Clients: ${slugs.length > 0 ? slugs.join(", ") : "(single-client mode)"}`);
  console.log(`  Commands: /analytics, /geolift`);

  // Auto-join the experiment channel so the bot receives messages
  if (EXPERIMENT_CHANNEL_ID) {
    try {
      await app.client.conversations.join({
        token: process.env.SLACK_BOT_TOKEN,
        channel: EXPERIMENT_CHANNEL_ID,
      });
      console.log(`  Joined channel ${EXPERIMENT_CHANNEL_ID}`);
    } catch (e) {
      console.log(`  Could not join channel ${EXPERIMENT_CHANNEL_ID}:`, e instanceof Error ? e.message : e);
    }
  }

  // Start polling for completed experiments
  if (EXPERIMENT_CHANNEL_ID) {
    console.log(`  Results polling enabled for channel ${EXPERIMENT_CHANNEL_ID}`);
    setInterval(pollCompletedExperiments, POLL_INTERVAL_MS);
  } else {
    console.log(`  Results polling disabled (set SLACK_EXPERIMENT_CHANNEL_ID to enable)`);
  }
})();
