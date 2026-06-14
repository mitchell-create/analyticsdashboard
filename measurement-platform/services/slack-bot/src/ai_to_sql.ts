/**
 * ai_to_sql.ts — Hybrid: pattern matching first, LLM fallback when no pattern matches.
 * Report mode: "make a report" / "ecom summary" → multi-query → text summary + tables (Option A).
 */

import OpenAI from "openai";
import { isSqlAllowed, extractTablesUsed } from "./guardrails";
import { runReadOnlyQuery, logQueryAudit } from "./db";
import type { ThreadMessage } from "./types";

const SCHEMA = "public_marts";
const MAX_REPORT_METRICS = 8;
const MAX_ROWS_PER_TABLE = 5;

/** Format a value for report display (currency, decimals, commas). */
function formatReportValue(val: unknown, columnName = ""): string {
  if (val === null || val === undefined) return "—";
  const str = String(val);
  const lower = columnName.toLowerCase();
  const num = Number(val);
  if (Number.isNaN(num)) return str;
  if (lower.includes("revenue") || lower.includes("spend") || lower.includes("value") || lower.includes("cost") || lower.includes("total_spend") || lower.includes("total_revenue")) {
    return "$" + num.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }
  if (lower.includes("percent") || lower.includes("change")) return num.toFixed(1) + "%";
  if (lower.includes("roas")) return num.toFixed(2) + "x";
  if (Number.isInteger(num) || (num > 100 && !lower.includes("rate"))) {
    return num.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }
  return num.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

/** Format a table row for display with clean numbers. */
function formatReportRow(row: Record<string, unknown>, keys: string[]): string {
  return keys.map((k) => formatReportValue(row[k], k)).join(" | ");
}

/** Clean column header for display (total_revenue → Total Revenue). */
function cleanHeader(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Parse period days from prompt (e.g. "past 7 days" → 7). */
function parsePeriodDays(prompt: string): number {
  const lower = prompt.toLowerCase();
  const m = lower.match(/(?:past|last)\s+(\d+)\s+days?/);
  if (m) return Math.min(90, Math.max(1, parseInt(m[1], 10)));
  if (/\b(week|7\s*day)/.test(lower)) return 7;
  if (/\b(month|30\s*day)/.test(lower)) return 30;
  return 30;
}

/** Detect comparison request: "compare", "vs", "vs previous", "percentage change". */
function isComparisonRequest(prompt: string): boolean {
  const lower = prompt.toLowerCase();
  return /\b(compare|vs\.?|versus|vs previous|prior period|percentage change|% change|percent change)\b/.test(lower);
}

function getSchemaHint(): string {
  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const year = new Date().getFullYear();
  return `
Today's date is ${today}. The current year is ${year}.

Tables (use public_marts schema for aggregated data, raw schema for platform-specific details):

Aggregated / mart tables:
- public_marts.fact_spend_daily (client_slug, report_date, channel ['meta','google','tiktok','tiktok_gmvmax'], spend, impressions, clicks)
- public_marts.fact_spend_daily_fx (client_slug, report_date, channel, spend — FX-converted, impressions, clicks)
- public_marts.fact_kpi_daily (client_slug, report_date, revenue, orders)
- public_marts.fact_kpi_geo_daily (report_date, geo_id, revenue, orders)
- public_marts.fact_tiktok_gmvmax_daily (client_slug, report_date, spend, orders, revenue, cost_per_order, roas) — TikTok Shop / GMV Max campaigns (Chubble only)
- public_marts.fact_customers_daily (report_date, new_customers, returning_customers, total_customers)
- public_marts.dim_geo (geo_id, geo_name, geo_type)
- public_marts.dim_customers (customer_identifier, first_order_date, last_order_date, days_with_orders, total_orders, lifetime_revenue, is_new_customer_last_year, days_since_first_order)
- public.fact_tiktok_organic_daily (report_date, views, likes, comments, shares, followers)
- public.marketing_events (event_date, event_type, event_name)
- public.experiments, public.experiment_results

Raw platform tables (for deep-dive metrics):
- raw.meta_ads_insights (date_start, account_id, spend, impressions, inline_link_clicks, unique_inline_link_clicks, frequency, cpm, cpc, ctr, reach)
- raw.google_account_performance_report (segments_date, customer_id, metrics_cost_micros, metrics_impressions, metrics_clicks, metrics_ctr, metrics_conversions, metrics_conversions_value, metrics_average_cpc, metrics_average_cpm, metrics_cost_per_conversion, metrics_conversions_from_interactions_rate)
- raw.tiktok_advertisers_reports_daily (advertiser_id, stat_time_day, metrics->'spend', metrics->'impressions', metrics->'clicks')
- public_marts.client_ad_accounts (client_slug, platform, account_id) — maps ad platform accounts to clients

Notes:
- When the user says a month name without a year (e.g. "Feb", "January"), ALWAYS assume the current year (${year}). Use CURRENT_DATE-based expressions or explicit ${year} dates. NEVER default to old years.
- client_slug identifies the client/brand (e.g. 'expand', 'chubble'). It exists on fact_spend_daily, fact_spend_daily_fx, fact_kpi_daily, fact_tiktok_gmvmax_daily. Do NOT use client_slug on raw tables — join with client_ad_accounts instead.
- channel values: 'meta' (Meta/Facebook), 'google' (Google Ads), 'tiktok' (TikTok regular web ads), 'tiktok_gmvmax' (TikTok Shop GMV Max). Channel is NOT a client name.
- TikTok regular ads (channel='tiktok') have spend/impressions/clicks. TikTok GMV Max (channel='tiktok_gmvmax') has spend but NULL impressions/clicks — use fact_tiktok_gmvmax_daily for orders/revenue/ROAS.
- Meta "clicks" = inline_link_clicks (link clicks only, not total clicks)
- Google spend = metrics_cost_micros / 1000000
- Google ROAS = metrics_conversions_value / (metrics_cost_micros / 1000000)
`;
}

/**
 * Detect report request: "make a report", "ecom summary", "summary for past month", etc.
 */
function isReportRequest(prompt: string): boolean {
  const lower = prompt.toLowerCase().trim();
  const reportPhrases = [
    "make a report",
    "create a report",
    "ecom summary",
    "ecommerce summary",
    "marketing summary",
    "summary report",
    "weekly report",
    "monthly report",
    "give me a report",
    "generate a report",
    "summary for",
    "report showing",
    "report that shows",
    "compare past",
    "compare last",
  ];
  return reportPhrases.some((p) => lower.includes(p));
}

/**
 * Report mode: generate multiple SQL queries via LLM, run them, return summary + tables.
 * Supports comparison mode: "past 7 days vs previous 7 days" → Current | Prior | % Change
 */
async function answerReportQuery(
  prompt: string,
  options: { userId?: string; channelId?: string; clientSlug?: string }
): Promise<{ text: string; error?: string }> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return {
      text: "Report mode requires OPENAI_API_KEY. Add it to .env to use 'make a report' or 'ecom summary'.",
    };
  }

  const comparisonMode = isComparisonRequest(prompt);
  const periodDays = parsePeriodDays(prompt);
  const currentEnd = "CURRENT_DATE";
  const currentStart = `CURRENT_DATE - INTERVAL '${periodDays} days'`;
  const priorEnd = `CURRENT_DATE - INTERVAL '${periodDays} days'`;
  const priorStart = `CURRENT_DATE - INTERVAL '${periodDays * 2} days'`;

  const clientContext = options.clientSlug && options.clientSlug !== "default"
    ? `\nIMPORTANT: The current client is '${options.clientSlug}'. ALWAYS add WHERE client_slug = '${options.clientSlug}' when querying fact_spend_daily or fact_kpi_daily.`
    : "";

  try {
    const client = new OpenAI({ apiKey });

    const systemPrompt = comparisonMode
      ? `You are a SQL expert for a marketing analytics database. The user wants a REPORT with COMPARISON (current vs prior period).

${getSchemaHint()}

Current period: report_date >= ${currentStart} AND report_date < ${currentEnd}
Prior period: report_date >= ${priorStart} AND report_date < ${priorEnd}
${clientContext}

Generate ${MAX_REPORT_METRICS} PostgreSQL SELECT queries. Each query MUST return a single row with exactly two numeric columns aliased as "current" and "prior".
Format each as:
METRIC: <short label>
SQL: <single SELECT query>

Example for total revenue:
SELECT
  SUM(CASE WHEN report_date >= ${currentStart} AND report_date < ${currentEnd} THEN revenue ELSE 0 END) as current,
  SUM(CASE WHEN report_date >= ${priorStart} AND report_date < ${priorEnd} THEN revenue ELSE 0 END) as prior
FROM public_marts.fact_kpi_daily${options.clientSlug && options.clientSlug !== "default" ? ` WHERE client_slug = '${options.clientSlug}'` : ""}

For breakdowns (e.g. spend by channel), return multiple rows with dimension column first, then "current" and "prior".
Rules: Only SELECT. Use public_marts. No explanation, just METRIC/SQL pairs.`
      : `You are a SQL expert for a marketing analytics database. The user wants a REPORT with multiple metrics.

${getSchemaHint()}
${clientContext}

Generate exactly ${MAX_REPORT_METRICS} PostgreSQL SELECT queries. Format each as:
METRIC: <short label>
SQL: <single SELECT query>

Rules:
- Only SELECT. No INSERT, UPDATE, DELETE, DROP.
- Use public_marts schema. Filter to past ${periodDays} days (report_date >= CURRENT_DATE - INTERVAL '${periodDays} days') unless the user specifies otherwise.
- Each query should return a different metric (revenue, orders, spend by channel, ROAS, etc.).
- Use clear column aliases (total_revenue, total_orders, etc.).
- Limit each query to ${MAX_ROWS_PER_TABLE + 2} rows.
- No explanation, just METRIC/SQL pairs.`;

    const response = await client.chat.completions.create({
      model: process.env.OPENAI_SQL_MODEL || process.env.OPENAI_MODEL || "gpt-5.4",
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: prompt || "Ecommerce summary for the past month" },
      ],
      temperature: 0.1,
      max_completion_tokens: 2000,
    });

    const content = response.choices[0]?.message?.content?.trim();
    if (!content) return { text: "Could not generate report queries." };

    // Parse METRIC: ... SQL: ... pairs (flexible whitespace/newlines)
    const pairs: { label: string; sql: string }[] = [];
    const blocks = content.split(/(?=METRIC:)/i);
    for (const block of blocks) {
      if (pairs.length >= MAX_REPORT_METRICS) break;
      const metricMatch = block.match(/METRIC:\s*(.+?)(?=SQL:|$)/is);
      const sqlMatch = block.match(/SQL:\s*([\s\S]*?)(?=METRIC:|$)/is);
      if (!metricMatch || !sqlMatch) continue;
      const label = metricMatch[1].trim().replace(/\s+/g, " ");
      let sql = sqlMatch[1].trim();
      const codeBlock = sql.match(/```(?:sql)?\s*([\s\S]*?)```/);
      if (codeBlock) sql = codeBlock[1].trim();
      if (sql.toUpperCase().startsWith("SELECT")) {
        pairs.push({ label, sql });
      }
    }

    if (pairs.length === 0) return { text: "Could not parse report queries. Try: 'ecom summary for past month'." };

    const sections: string[] = [];
    const periodLabel = comparisonMode ? `Past ${periodDays} days vs previous ${periodDays} days` : `Past ${periodDays} days`;
    sections.push(`*📊 Report* (${pairs.length} metrics) — ${periodLabel}\n`);

    for (const { label, sql } of pairs) {
      const check = isSqlAllowed(sql);
      if (!check.allowed) {
        sections.push(`*${label}* — Skipped (${check.reason})`);
        continue;
      }

      const { data, error } = await runReadOnlyQuery(sql, options.clientSlug);
      await logQueryAudit({
        user_id: options.userId,
        channel_id: options.channelId,
        client_slug: options.clientSlug,
        prompt: `[Report] ${label}`,
        sql_executed: sql,
        table_used: extractTablesUsed(sql) ?? undefined,
        row_count: Array.isArray(data) ? data.length : 0,
        error_message: error?.message,
      }, options.clientSlug);

      if (error) {
        sections.push(`*${label}* — Error: ${error.message}`);
        continue;
      }

      if (!Array.isArray(data) || data.length === 0) {
        sections.push(`*${label}* — No data`);
        continue;
      }

      const rows = data.slice(0, MAX_ROWS_PER_TABLE);
      const keys = Object.keys(rows[0] as Record<string, unknown>);

      if (comparisonMode && keys.length >= 2) {
        // Look for current/prior columns (case-insensitive)
        const currentKey = keys.find((k) => k.toLowerCase() === "current") ?? keys[keys.length - 2];
        const priorKey = keys.find((k) => k.toLowerCase() === "prior") ?? keys[keys.length - 1];
        const dimKey = keys.length > 2 ? keys[0] : null;
        const header = dimKey ? `${cleanHeader(dimKey)} | Current | Prior | Change` : "Current | Prior | Change";
        const lines = rows.map((r) => {
          const row = r as Record<string, unknown>;
          const curr = Number(row[currentKey]) || 0;
          const prev = Number(row[priorKey]) || 0;
          const pct = prev !== 0 ? ((curr - prev) / prev) * 100 : (curr > 0 ? 100 : 0);
          const changeStr = pct >= 0 ? `+${pct.toFixed(1)}%` : `${pct.toFixed(1)}%`;
          const dimVal = dimKey ? String(row[dimKey] ?? "") : "";
          const currStr = formatReportValue(curr, currentKey);
          const prevStr = formatReportValue(prev, priorKey);
          return dimKey ? `${dimVal} | ${currStr} | ${prevStr} | ${changeStr}` : `${currStr} | ${prevStr} | ${changeStr}`;
        });
        const table = [header, ...lines].join("\n");
        sections.push(`*${label}*\n\`\`\`\n${table}\n\`\`\``);
      } else {
        const header = keys.map(cleanHeader).join(" | ");
        const lines = rows.map((r) => formatReportRow(r as Record<string, unknown>, keys));
        const table = [header, ...lines].join("\n");
        const more = data.length > MAX_ROWS_PER_TABLE ? ` (+${data.length - MAX_ROWS_PER_TABLE} more)` : "";
        sections.push(`*${label}*${more}\n\`\`\`\n${table}\n\`\`\``);
      }
    }

    return { text: sections.join("\n\n") };
  } catch (err) {
    console.error("Report generation failed:", err);
    return {
      text: `Report failed: ${err instanceof Error ? err.message : String(err)}`,
      error: err instanceof Error ? err.message : undefined,
    };
  }
}

/**
 * Pattern matching: returns SQL when a known intent matches, null otherwise.
 * When clientSlug is provided, injects client_slug filtering into queries on tables that support it.
 */
function promptToSqlPatterns(prompt: string, clientSlug?: string): string | null {
  const lower = prompt.toLowerCase().trim();
  if (!lower || lower.length < 2) return null;

  // Helper: add client_slug WHERE clause for tables that have it
  const clientFilter = clientSlug && clientSlug !== "default"
    ? ` AND client_slug = '${clientSlug}'`
    : "";

  // Texas / geo revenue
  if (lower.includes("texas") && (lower.includes("spend") || lower.includes("revenue"))) {
    return `SELECT f.report_date, f.geo_id, f.revenue, f.orders FROM ${SCHEMA}.fact_kpi_geo_daily f JOIN ${SCHEMA}.dim_geo g ON f.geo_id = g.geo_id WHERE g.geo_name ILIKE '%Texas%' AND (f.revenue > 0 OR f.orders > 0) AND f.report_date >= CURRENT_DATE - INTERVAL '90 days' ORDER BY f.report_date DESC LIMIT 31`;
  }
  // TikTok organic (table is in public schema, not public_marts)
  if (lower.includes("tiktok") && (lower.includes("spike") || lower.includes("views"))) {
    return `SELECT report_date, views, likes FROM public.fact_tiktok_organic_daily ORDER BY report_date DESC LIMIT 14`;
  }
  // Anomalies / data quality
  if (lower.includes("anomal") || lower.includes("yesterday")) {
    return `SELECT * FROM public.data_quality_flags WHERE flag_date >= CURRENT_DATE - INTERVAL '1 day' ORDER BY created_at DESC LIMIT 20`;
  }
  // Spend by channel (explicit)
  if ((lower.includes("spend") || lower.includes("spending")) && (lower.includes("channel") || lower.includes("by channel"))) {
    return `SELECT report_date, channel, spend, impressions, clicks FROM ${SCHEMA}.fact_spend_daily WHERE 1=1${clientFilter} ORDER BY report_date DESC LIMIT 30`;
  }
  // Revenue / orders (generic)
  if ((lower.includes("revenue") || lower.includes("orders")) && !lower.includes("geo") && !lower.includes("state") && !lower.includes("texas") && !lower.includes("california")) {
    return `SELECT report_date, revenue, orders FROM ${SCHEMA}.fact_kpi_daily WHERE 1=1${clientFilter} ORDER BY report_date DESC LIMIT 30`;
  }

  return null;
}

/**
 * LLM fallback: call OpenAI to generate SQL from natural language.
 * When clientSlug is provided, instructs the LLM to filter by client_slug.
 */
async function promptToSqlLLM(prompt: string, clientSlug?: string, threadContext?: ThreadMessage[]): Promise<string | null> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) return null;

  const clientContext = clientSlug && clientSlug !== "default"
    ? `\n- IMPORTANT: The current client is '${clientSlug}'. ALWAYS add WHERE client_slug = '${clientSlug}' when querying fact_spend_daily or fact_kpi_daily, even if the user doesn't mention the client name.`
    : "";

  try {
    const client = new OpenAI({ apiKey });

    const systemPrompt = `You are a SQL expert for a marketing analytics database. Generate ONLY a single PostgreSQL SELECT query. No explanation, no markdown. Use these tables:

${getSchemaHint()}

Rules:
- Only SELECT. No INSERT, UPDATE, DELETE, DROP.
- Use public_marts schema for fact/dim tables.
- Limit results to 50 rows unless the question asks for more.
- Use report_date for date filtering when relevant.${clientContext}
- If the user is NOT asking for data but instead wants you to modify, rewrite, add narrative/context to a previous report, or discuss strategy, respond with exactly: NARRATIVE_MODE`;

    // Build messages array with thread context for multi-turn conversations
    const messages: Array<{ role: "system" | "user" | "assistant"; content: string }> = [
      { role: "system", content: systemPrompt },
    ];
    if (threadContext && threadContext.length > 0) {
      for (const msg of threadContext) {
        messages.push({ role: msg.role, content: msg.content });
      }
    }
    messages.push({ role: "user", content: prompt });

    const response = await client.chat.completions.create({
      model: process.env.OPENAI_SQL_MODEL || process.env.OPENAI_MODEL || "gpt-5.4",
      messages,
      temperature: 0.1,
      max_completion_tokens: 500,
    });

    const content = response.choices[0]?.message?.content?.trim();
    if (!content) return null;

    // Check if the LLM determined this is a narrative request
    if (content === "NARRATIVE_MODE") return "NARRATIVE_MODE";

    // Extract SQL (may be wrapped in ```sql ... ```)
    let sql = content;
    const codeBlock = content.match(/```(?:sql)?\s*([\s\S]*?)```/);
    if (codeBlock) sql = codeBlock[1].trim();
    if (!sql.toUpperCase().startsWith("SELECT")) return null;

    return sql;
  } catch (err) {
    console.error("LLM SQL generation failed:", err);
    return null;
  }
}

/**
 * Resolve prompt to SQL: try patterns first, then LLM fallback.
 * clientSlug is passed through so queries are scoped to the active client.
 */
async function promptToSql(prompt: string, clientSlug?: string, threadContext?: ThreadMessage[]): Promise<string | null> {
  const patternSql = promptToSqlPatterns(prompt, clientSlug);
  if (patternSql) return patternSql;

  const llmSql = await promptToSqlLLM(prompt, clientSlug, threadContext);
  return llmSql;
}

/**
 * Detect narrative/editorial requests that don't need SQL.
 * These are requests to modify, annotate, or rewrite a previous report with commentary.
 */
function isNarrativeRequest(prompt: string, threadContext?: ThreadMessage[]): boolean {
  const lower = prompt.toLowerCase();
  // Only applies in threads (needs prior report context to modify)
  if (!threadContext || threadContext.length === 0) return false;
  const narrativeSignals = [
    "modify", "rewrite", "add narrative", "add context", "add commentary",
    "include the narrative", "include a narrative", "include context",
    "add a note", "add explanation", "explain why", "because of",
    "update the report", "change the wording", "adjust the tone",
    "make it sound", "rephrase", "editorial", "write up",
    "put together a", "summarize with", "add insight",
    "consumer behavior", "market conditions", "we discussed",
    "client mentioned", "due to", "likely why",
  ];
  return narrativeSignals.some((s) => lower.includes(s));
}

/**
 * Handle narrative/editorial requests: take prior report from thread context
 * and modify it with the user's commentary/narrative instructions.
 */
async function answerNarrativeRequest(
  prompt: string,
  options: { userId?: string; channelId?: string; clientSlug?: string; threadContext?: ThreadMessage[] }
): Promise<{ text: string; error?: string }> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return { text: "Narrative editing requires OPENAI_API_KEY. Add it to .env." };
  }

  const clientName = options.clientSlug && options.clientSlug !== "default"
    ? options.clientSlug.replace(/_/g, " ")
    : "the client";

  try {
    const client = new OpenAI({ apiKey });
    const messages: Array<{ role: "system" | "user" | "assistant"; content: string }> = [
      {
        role: "system",
        content: `You are a marketing analytics report writer. The user is in a conversation thread where a data report was previously generated. They want you to modify, annotate, or rewrite the report with additional narrative, context, or commentary.

Your job:
- Take the previous report from the thread history
- Apply the user's requested changes (add narrative, explain trends, include context, etc.)
- Return the modified report as a complete, polished Slack message
- Use Slack formatting: *bold* for headers, _italic_ for emphasis. Write numbers plainly (e.g. $21,220 not wrapped in backticks or code blocks)
- Keep the original data/numbers intact — only modify the narrative and commentary around them
- Write professionally but conversationally, as if presenting to the client
- The client name is "${clientName}"`
      },
    ];

    // Add thread context
    if (options.threadContext) {
      for (const msg of options.threadContext) {
        messages.push({ role: msg.role, content: msg.content });
      }
    }
    messages.push({ role: "user", content: prompt });

    const response = await client.chat.completions.create({
      model: process.env.OPENAI_MODEL || "gpt-4o",
      messages,
      temperature: 0.7,
      max_completion_tokens: 2000,
    });

    const content = response.choices[0]?.message?.content?.trim();
    return { text: content || "Could not generate narrative. Try rephrasing your request." };
  } catch (err) {
    console.error("Narrative generation failed:", err);
    return {
      text: `Narrative generation failed: ${err instanceof Error ? err.message : String(err)}`,
      error: err instanceof Error ? err.message : undefined,
    };
  }
}

/**
 * Resolve prompt to SQL, validate, run, audit, return result text.
 * Report requests ("make a report", "ecom summary") use multi-query flow.
 * Narrative requests (modify report, add context) use text generation.
 */
export async function answerQuery(
  prompt: string,
  options: { userId?: string; channelId?: string; clientSlug?: string; threadContext?: ThreadMessage[] }
): Promise<{ text: string; error?: string }> {
  // Report mode: multi-query summary + tables
  if (isReportRequest(prompt)) {
    return answerReportQuery(prompt, options);
  }

  const sql = await promptToSql(prompt, options.clientSlug, options.threadContext);

  // LLM determined this is a narrative/editorial request, not a data query
  if (sql === "NARRATIVE_MODE") {
    return answerNarrativeRequest(prompt, options);
  }

  if (!sql) {
    // If we're in a thread, try narrative mode as fallback
    if (options.threadContext && options.threadContext.length > 0) {
      return answerNarrativeRequest(prompt, options);
    }
    const hasKey = !!process.env.OPENAI_API_KEY;
    return {
      text: hasKey
        ? "I couldn't understand that question. Try rephrasing or ask about spend, revenue, orders, or channels."
        : "I couldn't map that question. Add OPENAI_API_KEY to .env for flexible questions, or try: spend by channel, revenue in Texas, TikTok views.",
    };
  }

  const check = isSqlAllowed(sql);
  if (!check.allowed) {
    await logQueryAudit({
      user_id: options.userId,
      channel_id: options.channelId,
      client_slug: options.clientSlug,
      prompt,
      sql_executed: null,
      error_message: check.reason ?? "Blocked",
    }, options.clientSlug);
    return { text: `Query not allowed: ${check.reason ?? "blocked"}.` };
  }

  const { data, error } = await runReadOnlyQuery(sql, options.clientSlug);
  const tableUsed = extractTablesUsed(sql);
  const rowCount = Array.isArray(data) ? data.length : 0;

  await logQueryAudit({
    user_id: options.userId,
    channel_id: options.channelId,
    client_slug: options.clientSlug,
    prompt,
    sql_executed: sql,
    table_used: tableUsed ?? undefined,
    row_count: rowCount,
    error_message: error?.message,
  }, options.clientSlug);

  if (error) {
    return { text: `Error running query: ${error.message}`, error: error.message };
  }

  if (!Array.isArray(data) || data.length === 0) {
    return { text: "No rows returned." };
  }

  // Format as simple table (first 10 rows)
  const rows = data.slice(0, 10);
  const keys = Object.keys(rows[0] as Record<string, unknown>);
  const header = keys.map(cleanHeader).join(" | ");
  const lines = rows.map((r) => keys.map((k) => {
    const val = (r as Record<string, unknown>)[k];
    if (val === null || val === undefined) return "—";
    // Format Date objects as YYYY-MM-DD
    if (val instanceof Date) return val.toISOString().slice(0, 10);
    // Format numbers nicely
    return formatReportValue(val, k);
  }).join(" | "));
  const table = [header, ...lines].join("\n");
  const more = data.length > 10 ? `\n... and ${data.length - 10} more rows` : "";
  return { text: "```\n" + table + more + "\n```" };
}
