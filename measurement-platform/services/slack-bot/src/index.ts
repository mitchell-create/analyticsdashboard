/**
 * index.ts — Slack Bolt app: analytics Q&A, GeoLift experiments, and pipeline alerts.
 * Env: SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_DB_URL.
 */

import "dotenv/config";
import { App } from "@slack/bolt";
import { answerQuery } from "./ai_to_sql";
import { handleGeoliftCommand, isExperimentQuery, answerExperimentQuery, getNewlyCompletedResults } from "./experiment_agent";

const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  signingSecret: process.env.SLACK_SIGNING_SECRET,
  socketMode: false,
});

// ─── Channel messages ────────────────────────────────────────────────────────

app.message(async ({ message, client, say }) => {
  if (message.subtype) return;
  const text = "text" in message ? (message.text as string) : "";
  if (!text || text.length < 3) return;

  try {
    // Route to experiment agent if the message is about GeoLift/experiments
    if (isExperimentQuery(text)) {
      const reply = await answerExperimentQuery(text, {
        userId: message.user,
        channelId: message.channel,
      });
      await say({ text: reply, thread_ts: message.ts });
      return;
    }

    // Default: analytics agent (NL → SQL)
    const { text: reply } = await answerQuery(text, {
      userId: message.user,
      channelId: message.channel,
    });
    await say({ text: reply, thread_ts: message.ts });
  } catch (e) {
    const err = e instanceof Error ? e.message : String(e);
    await say({ text: `Error: ${err}`, thread_ts: message.ts });
  }
});

// ─── /analytics slash command ────────────────────────────────────────────────

app.command("/analytics", async ({ command, ack, say }) => {
  await ack();
  const prompt = command.text?.trim() || "Show recent spend by channel";
  try {
    const { text: reply } = await answerQuery(prompt, {
      userId: command.user_id,
      channelId: command.channel_id,
    });
    await say({ text: reply });
  } catch (e) {
    const err = e instanceof Error ? e.message : String(e);
    await say({ text: `Error: ${err}` });
  }
});

// ─── /geolift slash command ──────────────────────────────────────────────────

app.command("/geolift", async ({ command, ack, say }) => {
  await ack();
  const text = command.text?.trim() || "help";
  try {
    const reply = await handleGeoliftCommand(text, {
      userId: command.user_id,
      channelId: command.channel_id,
    });
    await say({ text: reply });
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

const port = Number(process.env.PORT) || 3000;
(async () => {
  await app.start(port);
  console.log(`Slack bot running on port ${port}`);
  console.log(`  /analytics — NL → SQL analytics queries`);
  console.log(`  /geolift  — GeoLift experiment management`);

  // Start polling for completed experiments
  if (EXPERIMENT_CHANNEL_ID) {
    console.log(`  Results polling enabled for channel ${EXPERIMENT_CHANNEL_ID}`);
    setInterval(pollCompletedExperiments, POLL_INTERVAL_MS);
  } else {
    console.log(`  Results polling disabled (set SLACK_EXPERIMENT_CHANNEL_ID to enable)`);
  }
})();
