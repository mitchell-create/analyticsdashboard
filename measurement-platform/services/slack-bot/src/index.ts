/**
 * index.ts — Slack Bolt app: Q&A (NL → SQL → answer), GeoLift experiments, multi-client routing.
 * Env: SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, CLIENT_REGISTRY_PATH (or legacy SUPABASE_* vars).
 */

import "dotenv/config";
import { App } from "@slack/bolt";
import { answerQuery } from "./ai_to_sql";
import { handleGeoliftCommand, isExperimentQuery, answerExperimentQuery, getNewlyCompletedResults } from "./experiment_agent";
import { loadClientRegistry, listClientSlugs } from "./client_registry";
import { resolveClient, setDefaultClient } from "./client_context";

const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  signingSecret: process.env.SLACK_SIGNING_SECRET,
  socketMode: false,
});

/** Build disambiguation message when client can't be resolved. */
function disambiguationMessage(): string {
  const slugs = listClientSlugs();
  return `Which client? I see: *${slugs.join(", ")}*.\nUse \`--client <name> <question>\` or \`/analytics set-default <name>\`.`;
}

// ─── Channel messages ────────────────────────────────────────────────────────

app.message(async ({ message, say }) => {
  if (message.subtype) return;
  const text = "text" in message ? (message.text as string) : "";
  if (!text || text.length < 3) return;

  const { client, cleanedText, ambiguous } = resolveClient(
    text,
    message.channel,
    message.user
  );

  if (ambiguous && !client) {
    await say({ text: disambiguationMessage(), thread_ts: message.ts });
    return;
  }

  const options = {
    userId: message.user,
    channelId: message.channel,
    clientSlug: client?.clientSlug,
  };

  try {
    let reply: string;
    if (isExperimentQuery(cleanedText)) {
      reply = await answerExperimentQuery(cleanedText, options);
    } else {
      const result = await answerQuery(cleanedText, options);
      reply = result.text;
    }

    const prefix = client && client.clientSlug !== "default"
      ? `_[${client.displayName}]_ `
      : "";
    await say({ text: prefix + reply, thread_ts: message.ts });
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

  try {
    const { text: reply } = await answerQuery(cleanedText, {
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

const port = Number(process.env.PORT) || 3001;
(async () => {
  loadClientRegistry();
  await app.start(port);
  const slugs = listClientSlugs();
  console.log(`Slack bot running on port ${port}`);
  console.log(`  Clients: ${slugs.length > 0 ? slugs.join(", ") : "(single-client mode)"}`);
  console.log(`  Commands: /analytics, /geolift`);

  // Start polling for completed experiments
  if (EXPERIMENT_CHANNEL_ID) {
    console.log(`  Results polling enabled for channel ${EXPERIMENT_CHANNEL_ID}`);
    setInterval(pollCompletedExperiments, POLL_INTERVAL_MS);
  } else {
    console.log(`  Results polling disabled (set SLACK_EXPERIMENT_CHANNEL_ID to enable)`);
  }
})();
