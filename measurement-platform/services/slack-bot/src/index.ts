/**
 * index.ts — Slack Bolt app: Q&A (NL → SQL → answer) and optional app_mention for alerts.
 * Env: SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_DB_URL.
 */

import "dotenv/config";
import { App } from "@slack/bolt";
import { answerQuery } from "./ai_to_sql";

const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  signingSecret: process.env.SLACK_SIGNING_SECRET,
  socketMode: false,
});

// Respond to messages in channels where the bot is invited (optional: use app_mention to limit)
app.message(async ({ message, client, say }) => {
  if (message.subtype) return;
  const text = "text" in message ? (message.text as string) : "";
  if (!text || text.length < 3) return;

  // Optional: only respond when @mentioned
  // if (!message.text?.includes(`<@${process.env.SLACK_BOT_USER_ID}>`)) return;

  try {
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

// Slash command for explicit Q&A (e.g. /analytics How much did we spend in Texas?)
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

const port = Number(process.env.PORT) || 3000;
(async () => {
  await app.start(port);
  console.log(`Slack bot running on port ${port}`);
})();
