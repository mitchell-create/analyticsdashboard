# Slack Bot Setup — Q&A + Pipeline Alerts

Two parts: **(A) Pipeline failure alerts** (Prefect → Slack) and **(B) Q&A bot** (natural language → SQL in Slack).

---

## Part A: Pipeline Failure Alerts

When the daily pipeline fails, Prefect posts a message to Slack. Follow [orchestration/prefect/SLACK_ALERTS_SETUP.md](../../orchestration/prefect/SLACK_ALERTS_SETUP.md) for full steps.

**Quick summary:**
1. Create a Slack app at [api.slack.com/apps](https://api.slack.com/apps) (From scratch)
2. Add **chat:write** scope, install to workspace, copy **Bot User OAuth Token** (starts with `xoxb-`)
3. Create a channel (e.g. `#measurement-alerts`), invite the bot (`/invite @YourAppName`)
4. Get channel ID (right-click channel → View details → scroll to bottom, or from URL `.../archives/C0123456789`)
5. Edit `orchestration/prefect/deployments/deploy.ps1` — uncomment and set:
   ```powershell
   $env:SLACK_BOT_TOKEN = "xoxb-your-token"
   $env:SLACK_ALERT_CHANNEL_ID = "C0123456789"
   ```
6. Run `.\orchestration\prefect\deployments\deploy.ps1` and restart the Prefect worker

---

## Part B: Q&A Bot (natural language → SQL)

The bot answers questions like "Spend in Texas last month?" by converting to SQL and querying Supabase.

### Prerequisites

- Node.js 18+
- Supabase tables: `ai_query_audit` (run `warehouse/schema/050_quality.sql` if not done)
- Slack app with **Event Subscriptions** and **Slash Commands** (see below)

### B.1 Create or reuse a Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Create new app (or reuse the one from Part A)
3. Add these **Bot Token Scopes** (OAuth & Permissions):
   - `chat:write`
   - `app_mentions:read` (optional, for @mentions)
   - `channels:history` (if bot reads channel messages)
   - `commands` (for /analytics slash command)

### B.2 Enable Event Subscriptions (for channel messages)

1. In app settings → **Event Subscriptions** → turn **On**
2. **Request URL:** You need a public URL. Options:
   - **ngrok:** Run `ngrok http 3001` and use `https://xxx.ngrok.io/slack/events`
   - **Deploy** to a server with HTTPS
3. Subscribe to **bot events:**
   - `message.channels` — bot sees messages in channels it's in
   - `app_mention` — bot sees when @mentioned (optional)
4. Save changes, **reinstall** the app to workspace

### B.3 Create Slash Commands (optional but easier)

1. **Slash Commands** → **Create New Command** (create each):

   | Command | Short description | Request URL |
   |---------|-------------------|-------------|
   | `/analytics` | Ask analytics questions | Same as Event Subscriptions (e.g. `https://xxx.ngrok.io/slack/events`) |
   | `/geolift` | GeoLift & experiment setup help | Same as above |

2. Save each command.

**Note:** Bolt handles both slash commands and events. Use the same Request URL as Event Subscriptions. For `/analytics`, the Request URL should point to your app. Bolt typically uses one URL for all events — check Bolt docs for your setup.

### B.4 Get Signing Secret

1. **Basic Information** → **App Credentials** → **Signing Secret**
2. Copy it (starts with a long hex string)

### B.5 Create .env file

In `services/slack-bot/` create `.env`:

```
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
SUPABASE_URL=https://xopsomagbnsnadxxhzhx.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
SUPABASE_DB_URL=postgresql://postgres.xopsomagbnsnadxxhzhx:YOUR_PASSWORD@aws-1-us-east-2.pooler.supabase.com:5432/postgres
PORT=3001

# Optional: OpenAI API key for flexible questions (LLM fallback when no pattern matches)
OPENAI_API_KEY=sk-your-openai-api-key
```

Replace with your actual values. Use the same Supabase credentials as your dbt/Metabase setup. Add `OPENAI_API_KEY` for the hybrid model (pattern matching + LLM fallback).

### B.6 Install and run

```powershell
cd "C:\Users\ReadyPlayerOne\Analytics Dashboard\measurement-platform\services\slack-bot"
npm install
npm run build
npm start
```

The bot runs on port 3001. For Slack to reach it, use **ngrok**:

```powershell
ngrok http 3001
```

Use the ngrok HTTPS URL (e.g. `https://abc123.ngrok.io`) as your Event Subscriptions and Slash Command Request URL. For Bolt, the path is usually `/slack/events` for events.

### B.7 Test

1. Invite the bot to a channel
2. Type: `Spend by channel` or use `/analytics Spend by channel`
3. Bot should reply with a table of data

### B.8 Report mode (Option A)

With `OPENAI_API_KEY` set, you can request multi-metric reports:

- `/analytics make a report for the past month`
- `/analytics ecom summary`
- `/analytics marketing summary showing revenue, spend, and orders`

The bot generates up to 8 SQL queries, runs them, and returns a text summary with formatted tables (currency, commas, clean labels).

**Comparison mode** — Add "vs previous" or "compare" to get % change:

- `/analytics ecom summary past 7 days vs previous 7 days`
- `/analytics compare past 30 days to previous 30 days`

Shows: Current | Prior | % Change for each metric.

### B.9 GeoLift / experiment agent

With `OPENAI_API_KEY` set, you can get GeoLift and experiment setup guidance:

- `/geolift` — General setup and best practices
- `/geolift how do I choose treatment vs holdout geos?`
- `/geolift what's the minimum pre-period for a valid test?`
- In channel: "How do I run a GeoLift test?" or "Geo lift best practices"

The agent uses `gpt-4o` by default (set `OPENAI_AGENT_MODEL` to override) and fetches your current experiments from the DB for context.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "SUPABASE_DB_URL not set" | Add SUPABASE_DB_URL to .env with full postgres:// connection string |
| "relation marts.fact_xxx does not exist" | Tables are in `public_marts` schema; bot uses `public_marts` |
| Slack events not received | Ensure ngrok is running, URL is HTTPS, app reinstalled |
| "Query not allowed" | Check guardrails.ts allowlist; tables must be allowlisted |

---

## Schema note

The dbt project creates tables in `public_marts`. The bot's SQL uses `public_marts.fact_spend_daily` etc. If you see "relation does not exist", verify the schema name in Supabase (Table Editor → schema dropdown).
