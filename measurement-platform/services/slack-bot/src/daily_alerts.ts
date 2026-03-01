/**
 * daily_alerts.ts — Post pipeline/QA alerts to Slack (e.g. failed runs, data quality flags).
 * Call from Prefect or cron after daily_pipeline / qa_checks.
 */

import type { Block, KnownBlock } from "@slack/web-api";
import { WebClient } from "@slack/web-api";

/**
 * Post a message to a Slack channel. Uses SLACK_BOT_TOKEN and channel ID from env or argument.
 */
export async function postAlert(
  message: string,
  options: { channelId?: string; blocks?: (Block | KnownBlock)[] } = {}
): Promise<void> {
  const token = process.env.SLACK_BOT_TOKEN;
  const channelId = options.channelId ?? process.env.SLACK_ALERT_CHANNEL_ID;
  if (!token || !channelId) {
    console.warn("SLACK_BOT_TOKEN or SLACK_ALERT_CHANNEL_ID not set; skipping alert");
    return;
  }
  const client = new WebClient(token);
  await client.chat.postMessage({
    channel: channelId,
    text: message,
    blocks: options.blocks,
  });
}

/**
 * Format and post pipeline failure alert.
 */
export async function postPipelineFailure(
  flowName: string,
  runDate: string,
  errorMessage: string,
  channelId?: string
): Promise<void> {
  const text = `:x: *Pipeline failure*\nFlow: ${flowName}\nDate: ${runDate}\nError: ${errorMessage}`;
  await postAlert(text, { channelId });
}

/**
 * Format and post data quality alert (e.g. missing dates, anomalies).
 */
export async function postQualityAlert(
  checkName: string,
  severity: string,
  message: string,
  channelId?: string
): Promise<void> {
  const emoji = severity === "critical" ? ":rotating_light:" : severity === "error" ? ":warning:" : ":grey_exclamation:";
  const text = `${emoji} *Data quality*\nCheck: ${checkName}\nSeverity: ${severity}\n${message}`;
  await postAlert(text, { channelId });
}
