/**
 * diagnostic_report.ts — Multi-step diagnostic report generator.
 *
 * Flow:
 *   1. Parse period from prompt (calendar month or rolling days)
 *   2. Pull metrics via hardcoded SQL queries (reliable, no LLM for data)
 *   3. Calculate period-over-period changes, flag significant movers
 *   4. Feed all data to LLM for narrative analysis + strategy recommendations
 *   5. Format with emoji indicators matching the team's report style
 *
 * Trigger phrases: "monthly report", "diagnostic report", "performance report",
 *   "ads report", "marketing report", "generate report", "full report"
 */

import OpenAI from "openai";
import { runReadOnlyQuery, logQueryAudit } from "./db";

// ─── Types ───────────────────────────────────────────────────────────────────

interface PeriodParams {
  currentStart: string; // e.g., '2026-01-01'
  currentEnd: string;   // e.g., '2026-02-01' (exclusive)
  priorStart: string;   // e.g., '2025-12-01'
  priorEnd: string;     // e.g., '2026-01-01' (exclusive)
  label: string;        // e.g., 'January 2026 vs December 2025'
}

interface Metric {
  name: string;
  current: number;
  prior: number;
  change: number;       // percentage change
  format: "currency" | "number" | "percent" | "roas" | "decimal";
  direction: "up-good" | "down-good" | "neutral";
  section: "overall" | "google" | "meta";
}

// ─── Period Parsing ──────────────────────────────────────────────────────────

const MONTH_MAP: Record<string, number> = {
  january: 0, jan: 0, february: 1, feb: 1, march: 2, mar: 2,
  april: 3, apr: 3, may: 4, june: 5, jun: 5,
  july: 6, jul: 6, august: 7, aug: 7, september: 8, sep: 8, sept: 8,
  october: 9, oct: 9, november: 10, nov: 10, december: 11, dec: 11,
};

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function monthLabel(d: Date): string {
  return d.toLocaleString("en-US", { month: "long", year: "numeric" });
}

/**
 * Parse the report period from the user's prompt.
 * Supports: "for January 2026", "for jan", "for last month", "past 30 days",
 *           or defaults to last complete calendar month.
 */
export function parseReportPeriod(prompt: string): PeriodParams {
  const lower = prompt.toLowerCase();
  const now = new Date();

  // ── Specific month: "for january 2026", "for dec", etc. ──
  const monthRx =
    /(?:for|in)\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)(?:\s+(\d{4}))?/;
  const mm = lower.match(monthRx);
  if (mm) {
    const monthNum = MONTH_MAP[mm[1]];
    let year = mm[2] ? parseInt(mm[2], 10) : now.getFullYear();
    // If target is in the future, assume previous year
    if (new Date(year, monthNum, 1) > now) year--;

    const curStart = new Date(year, monthNum, 1);
    const curEnd = new Date(year, monthNum + 1, 1);
    const priStart = new Date(year, monthNum - 1, 1);
    const priEnd = curStart;

    return {
      currentStart: `${curStart.getFullYear()}-${pad2(curStart.getMonth() + 1)}-01`,
      currentEnd: `${curEnd.getFullYear()}-${pad2(curEnd.getMonth() + 1)}-01`,
      priorStart: `${priStart.getFullYear()}-${pad2(priStart.getMonth() + 1)}-01`,
      priorEnd: `${priEnd.getFullYear()}-${pad2(priEnd.getMonth() + 1)}-01`,
      label: `${monthLabel(curStart)} vs ${monthLabel(priStart)}`,
    };
  }

  // ── Rolling days: "past 30 days", "last 7 days" ──
  const daysRx = /(?:past|last)\s+(\d+)\s+days?/;
  const dm = lower.match(daysRx);
  if (dm) {
    const days = Math.min(90, Math.max(1, parseInt(dm[1], 10)));
    return {
      currentStart: `CURRENT_DATE - INTERVAL '${days} days'`,
      currentEnd: `CURRENT_DATE`,
      priorStart: `CURRENT_DATE - INTERVAL '${days * 2} days'`,
      priorEnd: `CURRENT_DATE - INTERVAL '${days} days'`,
      label: `Past ${days} days vs previous ${days} days`,
    };
  }

  // ── Default: last complete calendar month vs the one before ──
  const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const twoAgo = new Date(now.getFullYear(), now.getMonth() - 2, 1);
  const thisMonth = new Date(now.getFullYear(), now.getMonth(), 1);

  return {
    currentStart: `${lastMonth.getFullYear()}-${pad2(lastMonth.getMonth() + 1)}-01`,
    currentEnd: `${thisMonth.getFullYear()}-${pad2(thisMonth.getMonth() + 1)}-01`,
    priorStart: `${twoAgo.getFullYear()}-${pad2(twoAgo.getMonth() + 1)}-01`,
    priorEnd: `${lastMonth.getFullYear()}-${pad2(lastMonth.getMonth() + 1)}-01`,
    label: `${monthLabel(lastMonth)} vs ${monthLabel(twoAgo)}`,
  };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function pctChange(current: number, prior: number): number {
  if (prior === 0) return current > 0 ? 100 : 0;
  return ((current - prior) / prior) * 100;
}

function metric(
  name: string,
  current: number,
  prior: number,
  format: Metric["format"],
  direction: Metric["direction"],
  section: Metric["section"],
): Metric {
  return { name, current, prior, change: pctChange(current, prior), format, direction, section };
}

/** Safe number extraction from query row. */
function num(row: Record<string, unknown>, key: string): number {
  return Number(row[key]) || 0;
}

/** Build a period CASE expression for a date column. */
function periodCase(
  dateCol: string,
  p: PeriodParams,
  agg: string,
  valueExpr: string,
  alias: string,
): string {
  const curWhere = `${dateCol} >= '${p.currentStart}' AND ${dateCol} < '${p.currentEnd}'`;
  const priWhere = `${dateCol} >= '${p.priorStart}' AND ${dateCol} < '${p.priorEnd}'`;
  return [
    `${agg}(CASE WHEN ${curWhere} THEN ${valueExpr} ELSE ${agg === "AVG" ? "NULL" : "0"} END) as cur_${alias}`,
    `${agg}(CASE WHEN ${priWhere} THEN ${valueExpr} ELSE ${agg === "AVG" ? "NULL" : "0"} END) as pri_${alias}`,
  ].join(",\n      ");
}

// ─── Data Pulling ────────────────────────────────────────────────────────────

async function pullOverallKPIs(p: PeriodParams, clientSlug?: string): Promise<Metric[]> {
  const metrics: Metric[] = [];
  const dc = "report_date";
  const clientFilter = clientSlug ? ` AND client_slug = '${clientSlug}'` : "";

  // Revenue & Orders
  const kpiSql = `
    SELECT
      ${periodCase(dc, p, "SUM", "revenue", "revenue")},
      ${periodCase(dc, p, "SUM", "orders", "orders")}
    FROM public_marts.fact_kpi_daily
    WHERE 1=1${clientFilter}
  `;
  const { data: kpi } = await runReadOnlyQuery(kpiSql, clientSlug);
  let curRev = 0, priRev = 0, curOrd = 0, priOrd = 0;
  if (kpi?.length) {
    const r = kpi[0] as Record<string, unknown>;
    curRev = num(r, "cur_revenue"); priRev = num(r, "pri_revenue");
    curOrd = num(r, "cur_orders");  priOrd = num(r, "pri_orders");
    metrics.push(metric("Revenue", curRev, priRev, "currency", "up-good", "overall"));
    metrics.push(metric("Orders", curOrd, priOrd, "number", "up-good", "overall"));
    metrics.push(metric("AOV", curOrd > 0 ? curRev / curOrd : 0, priOrd > 0 ? priRev / priOrd : 0, "currency", "up-good", "overall"));
  }

  // Total Spend
  const spendSql = `
    SELECT
      ${periodCase(dc, p, "SUM", "spend", "spend")}
    FROM public_marts.fact_spend_daily
    WHERE 1=1${clientFilter}
  `;
  const { data: sp } = await runReadOnlyQuery(spendSql, clientSlug);
  if (sp?.length) {
    const r = sp[0] as Record<string, unknown>;
    const curSpend = num(r, "cur_spend"), priSpend = num(r, "pri_spend");
    metrics.push(metric("Total Ad Spend", curSpend, priSpend, "currency", "neutral", "overall"));
    metrics.push(metric("MER (Blended ROAS)", curSpend > 0 ? curRev / curSpend : 0, priSpend > 0 ? priRev / priSpend : 0, "roas", "up-good", "overall"));
    metrics.push(metric("CPA", curOrd > 0 ? curSpend / curOrd : 0, priOrd > 0 ? priSpend / priOrd : 0, "currency", "down-good", "overall"));
  }

  return metrics;
}

async function pullGoogleMetrics(p: PeriodParams, clientSlug?: string): Promise<Metric[]> {
  const metrics: Metric[] = [];
  const dc = "segments_date::date";

  // Filter by client's Google account_id via client_ad_accounts mapping
  // Cast customer_id to text to match client_ad_accounts.account_id (text type)
  const accountFilter = clientSlug
    ? ` WHERE g.customer_id::text IN (SELECT account_id FROM public_marts.client_ad_accounts WHERE client_slug = '${clientSlug}' AND platform = 'google')`
    : "";

  const sql = `
    SELECT
      ${periodCase(dc, p, "SUM", "metrics_cost_micros::numeric / 1000000", "spend")},
      ${periodCase(dc, p, "SUM", "metrics_conversions_value::numeric", "conv_value")},
      ${periodCase(dc, p, "SUM", "metrics_conversions::numeric", "conversions")},
      ${periodCase(dc, p, "SUM", "metrics_impressions::numeric", "impressions")},
      ${periodCase(dc, p, "SUM", "metrics_clicks::numeric", "clicks")}
    FROM raw.google_account_performance_report g${accountFilter}
  `;

  const { data, error } = await runReadOnlyQuery(sql, clientSlug);
  if (error || !data?.length) {
    console.warn("Google metrics query failed:", error?.message);
    return metrics;
  }

  const r = data[0] as Record<string, unknown>;
  const curSpend = num(r, "cur_spend"),       priSpend = num(r, "pri_spend");
  const curCV    = num(r, "cur_conv_value"),   priCV    = num(r, "pri_conv_value");
  const curConv  = num(r, "cur_conversions"),  priConv  = num(r, "pri_conversions");
  const curImp   = num(r, "cur_impressions"),  priImp   = num(r, "pri_impressions");
  const curCl    = num(r, "cur_clicks"),       priCl    = num(r, "pri_clicks");

  metrics.push(metric("Google Spend",              curSpend, priSpend, "currency", "neutral", "google"));
  metrics.push(metric("Google ROAS (by Click)",    curSpend > 0 ? curCV / curSpend : 0, priSpend > 0 ? priCV / priSpend : 0, "roas", "up-good", "google"));
  metrics.push(metric("Google Conversions",        curConv, priConv, "number", "up-good", "google"));
  metrics.push(metric("Google Conversion Value",   curCV, priCV, "currency", "up-good", "google"));
  metrics.push(metric("Google Cost Per Conversion", curConv > 0 ? curSpend / curConv : 0, priConv > 0 ? priSpend / priConv : 0, "currency", "down-good", "google"));
  metrics.push(metric("Google CVR",                curCl > 0 ? (curConv / curCl) * 100 : 0, priCl > 0 ? (priConv / priCl) * 100 : 0, "percent", "up-good", "google"));
  metrics.push(metric("Google Impressions",        curImp, priImp, "number", "up-good", "google"));
  metrics.push(metric("Google Clicks",             curCl, priCl, "number", "up-good", "google"));
  metrics.push(metric("Google CTR",                curImp > 0 ? (curCl / curImp) * 100 : 0, priImp > 0 ? (priCl / priImp) * 100 : 0, "percent", "up-good", "google"));
  metrics.push(metric("Google CPC",                curCl > 0 ? curSpend / curCl : 0, priCl > 0 ? priSpend / priCl : 0, "currency", "down-good", "google"));

  return metrics;
}

async function pullMetaMetrics(p: PeriodParams, clientSlug?: string): Promise<Metric[]> {
  const metrics: Metric[] = [];
  const dc = "date_start::date";

  // Use account-level data for accurate totals
  const accountFilter = clientSlug
    ? ` WHERE m.account_id IN (SELECT account_id FROM public_marts.client_ad_accounts WHERE client_slug = '${clientSlug}' AND platform = 'meta')`
    : "";

  const sql = `
    SELECT
      ${periodCase(dc, p, "SUM", "spend::numeric", "spend")},
      ${periodCase(dc, p, "SUM", "impressions::numeric", "impressions")},
      ${periodCase(dc, p, "SUM", "inline_link_clicks::numeric", "clicks")},
      ${periodCase(dc, p, "SUM", "unique_inline_link_clicks::numeric", "unique_clicks")},
      ${periodCase(dc, p, "AVG", "frequency::numeric", "frequency")}
    FROM raw.meta_customaccount_insights_daily m${accountFilter}
  `;

  const { data, error } = await runReadOnlyQuery(sql, clientSlug);
  if (error || !data?.length) {
    console.warn("Meta metrics query failed:", error?.message);
    return metrics;
  }

  const r = data[0] as Record<string, unknown>;
  const curSpend  = num(r, "cur_spend"),         priSpend  = num(r, "pri_spend");
  const curImp    = num(r, "cur_impressions"),    priImp    = num(r, "pri_impressions");
  const curCl     = num(r, "cur_clicks"),         priCl     = num(r, "pri_clicks");
  const curUniq   = num(r, "cur_unique_clicks"),  priUniq   = num(r, "pri_unique_clicks");
  const curFreq   = num(r, "cur_frequency"),      priFreq   = num(r, "pri_frequency");

  metrics.push(metric("Meta Spend",       curSpend, priSpend, "currency", "neutral", "meta"));
  metrics.push(metric("Meta CPM",         curImp > 0 ? (curSpend / curImp) * 1000 : 0, priImp > 0 ? (priSpend / priImp) * 1000 : 0, "currency", "down-good", "meta"));
  metrics.push(metric("Meta Link CTR",    curImp > 0 ? (curCl / curImp) * 100 : 0, priImp > 0 ? (priCl / priImp) * 100 : 0, "percent", "up-good", "meta"));
  metrics.push(metric("Meta Unique CTR",  curImp > 0 ? (curUniq / curImp) * 100 : 0, priImp > 0 ? (priUniq / priImp) * 100 : 0, "percent", "up-good", "meta"));
  metrics.push(metric("Meta Frequency",   curFreq, priFreq, "decimal", "neutral", "meta"));
  metrics.push(metric("Meta CPC",         curCl > 0 ? curSpend / curCl : 0, priCl > 0 ? priSpend / priCl : 0, "currency", "down-good", "meta"));
  metrics.push(metric("Meta Impressions", curImp, priImp, "number", "up-good", "meta"));
  metrics.push(metric("Meta Link Clicks", curCl, priCl, "number", "up-good", "meta"));

  // Pull Meta actions: purchases, add to carts, checkouts, purchase value
  const actionsSql = `
    SELECT
      SUM(CASE WHEN ${dc} >= '${p.currentStart}' AND ${dc} < '${p.currentEnd}' THEN
        (SELECT COALESCE(SUM((elem->>'value')::numeric), 0) FROM jsonb_array_elements(m.actions) elem WHERE elem->>'action_type' = 'omni_purchase') ELSE 0 END) AS cur_purchases,
      SUM(CASE WHEN ${dc} >= '${p.priorStart}' AND ${dc} < '${p.priorEnd}' THEN
        (SELECT COALESCE(SUM((elem->>'value')::numeric), 0) FROM jsonb_array_elements(m.actions) elem WHERE elem->>'action_type' = 'omni_purchase') ELSE 0 END) AS pri_purchases,
      SUM(CASE WHEN ${dc} >= '${p.currentStart}' AND ${dc} < '${p.currentEnd}' THEN
        (SELECT COALESCE(SUM((elem->>'value')::numeric), 0) FROM jsonb_array_elements(m.actions) elem WHERE elem->>'action_type' = 'omni_add_to_cart') ELSE 0 END) AS cur_atc,
      SUM(CASE WHEN ${dc} >= '${p.priorStart}' AND ${dc} < '${p.priorEnd}' THEN
        (SELECT COALESCE(SUM((elem->>'value')::numeric), 0) FROM jsonb_array_elements(m.actions) elem WHERE elem->>'action_type' = 'omni_add_to_cart') ELSE 0 END) AS pri_atc,
      SUM(CASE WHEN ${dc} >= '${p.currentStart}' AND ${dc} < '${p.currentEnd}' THEN
        (SELECT COALESCE(SUM((elem->>'value')::numeric), 0) FROM jsonb_array_elements(m.actions) elem WHERE elem->>'action_type' = 'omni_initiated_checkout') ELSE 0 END) AS cur_checkouts,
      SUM(CASE WHEN ${dc} >= '${p.priorStart}' AND ${dc} < '${p.priorEnd}' THEN
        (SELECT COALESCE(SUM((elem->>'value')::numeric), 0) FROM jsonb_array_elements(m.actions) elem WHERE elem->>'action_type' = 'omni_initiated_checkout') ELSE 0 END) AS pri_checkouts,
      SUM(CASE WHEN ${dc} >= '${p.currentStart}' AND ${dc} < '${p.currentEnd}' THEN
        (SELECT COALESCE(SUM((elem->>'value')::numeric), 0) FROM jsonb_array_elements(m.action_values) elem WHERE elem->>'action_type' = 'omni_purchase') ELSE 0 END) AS cur_pv,
      SUM(CASE WHEN ${dc} >= '${p.priorStart}' AND ${dc} < '${p.priorEnd}' THEN
        (SELECT COALESCE(SUM((elem->>'value')::numeric), 0) FROM jsonb_array_elements(m.action_values) elem WHERE elem->>'action_type' = 'omni_purchase') ELSE 0 END) AS pri_pv
    FROM raw.meta_customaccount_insights_daily m${accountFilter}
  `;

  const { data: actData, error: actError } = await runReadOnlyQuery(actionsSql, clientSlug);
  if (!actError && actData?.length) {
    const a = actData[0] as Record<string, unknown>;
    const curPurch = num(a, "cur_purchases"), priPurch = num(a, "pri_purchases");
    const curATC = num(a, "cur_atc"), priATC = num(a, "pri_atc");
    const curCheckout = num(a, "cur_checkouts"), priCheckout = num(a, "pri_checkouts");
    const curPV = num(a, "cur_pv"), priPV = num(a, "pri_pv");

    metrics.push(metric("Meta Purchases", curPurch, priPurch, "number", "up-good", "meta"));
    metrics.push(metric("Meta Purchase Value", curPV, priPV, "currency", "up-good", "meta"));
    metrics.push(metric("Meta ROAS", curSpend > 0 ? curPV / curSpend : 0, priSpend > 0 ? priPV / priSpend : 0, "roas", "up-good", "meta"));
    metrics.push(metric("Meta AOV", curPurch > 0 ? curPV / curPurch : 0, priPurch > 0 ? priPV / priPurch : 0, "currency", "up-good", "meta"));
    metrics.push(metric("Meta Add to Carts", curATC, priATC, "number", "up-good", "meta"));
    metrics.push(metric("Meta Checkouts", curCheckout, priCheckout, "number", "up-good", "meta"));
    metrics.push(metric("Meta CVR", curCl > 0 ? (curPurch / curCl) * 100 : 0, priCl > 0 ? (priPurch / priCl) * 100 : 0, "percent", "up-good", "meta"));
  }

  return metrics;
}

// Meta ROAS is now calculated directly in pullMetaMetrics using account-level action_values

// ─── Formatting ──────────────────────────────────────────────────────────────

function fmtVal(value: number, format: Metric["format"]): string {
  switch (format) {
    case "currency":
      if (value >= 1000) return "$" + value.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
      return "$" + value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    case "number":
      return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
    case "percent":
      return value.toFixed(2) + "%";
    case "roas":
      return value.toFixed(2) + "x";
    case "decimal":
      return value.toFixed(2);
  }
}

function emojiFor(m: Metric): string {
  if (Math.abs(m.change) < 1) return "➡️";   // flat (<1% change)
  const up = m.change > 0;
  switch (m.direction) {
    case "up-good":   return up ? "🟢⬆️" : "🔴⬇️";
    case "down-good": return up ? "🔴⬆️" : "🟢⬇️";
    case "neutral":   return up ? "⬆️"   : "⬇️";
  }
}

function fmtMetric(m: Metric): string {
  const dir = m.change >= 0 ? "Up" : "Down";
  const abs = Math.abs(m.change).toFixed(1);
  return `${emojiFor(m)} *${m.name}:* ${abs}% ${dir} — ${fmtVal(m.prior, m.format)} → ${fmtVal(m.current, m.format)}`;
}

// ─── LLM Narrative ───────────────────────────────────────────────────────────

async function generateNarrative(
  metrics: Metric[],
  period: PeriodParams,
  clientDisplayName?: string,
): Promise<string> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return "_Analysis narrative requires OPENAI_API_KEY._";
  }

  const metricLines = metrics
    .map((m) => `${m.name} [${m.section}]: ${fmtVal(m.prior, m.format)} → ${fmtVal(m.current, m.format)} (${m.change >= 0 ? "+" : ""}${m.change.toFixed(1)}%)`)
    .join("\n");

  const significant = metrics
    .filter((m) => Math.abs(m.change) >= 5)
    .sort((a, b) => Math.abs(b.change) - Math.abs(a.change));
  const sigLines = significant.length
    ? significant.map((m) => `${m.name}: ${m.change >= 0 ? "+" : ""}${m.change.toFixed(1)}%`).join(", ")
    : "No significant changes (all metrics within ±5%)";

  const brandName = clientDisplayName || "the brand";

  const sysPrompt = `You are an expert performance marketing analyst writing a detailed monthly performance report for an e-commerce brand called ${brandName}.

Write a DETAILED WRITTEN REPORT in the following structure. This is a report that will be shared with the client — it should be professional, specific, and insightful.

REPORT STRUCTURE:

1. TITLE LINE: "${brandName} - [Current Month Year]"

2. NOTES ON RESULTS: Start with 1-2 sentences on overall revenue performance (up/down X% compared to prior month).

3. GOOGLE SECTION: "Google: Comparing [Current Month] to [Prior Month]"
   For each Google metric, write one line in this exact format:
   "[Metric Name] is [+/-X.XX%] [Up/Down] from [prior value] to [current value]"

   Include ALL of these metrics: Spend, ROAS By Click, Conversions, Conversion Value, Cost per Conversion, Conversion Rate, Impressions, Clicks, CTR, CPC.

   After the metrics, write 1-2 paragraphs of analysis explaining WHY the numbers moved the way they did. Reference specific metrics to support your reasoning. End with whether the channel is healthy or needs attention.

4. FACEBOOK/META SECTION: "Facebook: [Current Month] Performance Report"
   Write the same detailed metric lines for Meta: Spend, ROAS, Purchases, Purchase Value, AOV, CPM, Link CTR, Unique CTR, Frequency, CPC, Add to Carts, Checkouts, CVR, Impressions, Link Clicks.

   After the metrics, write 1-2 paragraphs of analysis. Comment on creative performance, audience saturation (frequency), retargeting vs prospecting balance, and what's working.

5. STRATEGY & PLAN GOING FORWARD:
   Provide 3-5 specific, actionable bullet points for next steps. Be concrete: "Test 3-5 new UGC mashup videos" not "improve creatives". Reference the data to justify each recommendation.

RULES:
- Write the FULL metric lines for every metric — do not skip any.
- Use actual numbers from the data provided — do not make up numbers.
- Each metric line must show the % change, direction (Up/Down), prior value, and current value.
- The analysis paragraphs should explain cause-and-effect, not just restate numbers.
- Diagnostic patterns to apply:
  * ROAS↓ + CPC↑ + CTR↓ → creative fatigue
  * CTR↓ + frequency↑ → audience saturation
  * Conversions↓ + clicks stable → landing page or checkout issue
  * Impressions↑ + CTR↓ → audience expansion diluting quality
  * Meta frequency > 2.5 → flag creative fatigue
- Do NOT use emoji or markdown formatting (no **, no ##).
- Use plain text only. Use line breaks between sections.
- Be thorough — this report should be 600-1000 words.`;

  const userPrompt = `Monthly performance data — ${period.label}:

${metricLines}

BIGGEST MOVERS (>5% change): ${sigLines}

Write the full detailed performance report.`;

  try {
    const client = new OpenAI({ apiKey });
    const res = await client.chat.completions.create({
      model: process.env.OPENAI_MODEL || "gpt-5.4",
      messages: [
        { role: "system", content: sysPrompt },
        { role: "user", content: userPrompt },
      ],
      temperature: 0.3,
      max_completion_tokens: 3000,
    });
    return res.choices[0]?.message?.content?.trim() || "Could not generate analysis.";
  } catch (err) {
    console.error("Narrative generation failed:", err);
    return `_Analysis failed: ${err instanceof Error ? err.message : String(err)}_`;
  }
}

// ─── Public API ──────────────────────────────────────────────────────────────

/**
 * Detect whether the prompt is asking for a diagnostic-style report.
 */
export function isDiagnosticReportRequest(prompt: string): boolean {
  const lower = prompt.toLowerCase().trim();
  const phrases = [
    "diagnostic report",
    "monthly report",
    "performance report",
    "ads report",
    "ad report",
    "marketing report",
    "generate report",
    "create report",
    "make a report",
    "make report",
    "full report",
    "channel report",
    "written report",
    "how did",
    "how were",
    "how was",
    "report for",
    "report that looks",
    "notes on results",
  ];
  return phrases.some((p) => lower.includes(p));
}

/**
 * Generate a full diagnostic report with metric breakdowns and AI analysis.
 */
export async function generateDiagnosticReport(
  prompt: string,
  options: { userId?: string; channelId?: string; clientSlug?: string; clientDisplayName?: string },
): Promise<string> {
  const period = parseReportPeriod(prompt);

  // Pull all metric groups in parallel (Meta ROAS now included in pullMetaMetrics)
  const [overallMetrics, googleMetrics, metaMetrics] = await Promise.all([
    pullOverallKPIs(period, options.clientSlug),
    pullGoogleMetrics(period, options.clientSlug),
    pullMetaMetrics(period, options.clientSlug),
  ]);

  const allMetrics = [...overallMetrics, ...googleMetrics, ...metaMetrics];

  if (allMetrics.length === 0) {
    return "No data available for the requested period. Verify that `fact_kpi_daily` and `fact_spend_daily` have data.";
  }

  // Resolve display name for the report title
  const displayName = options.clientDisplayName
    || (options.clientSlug ? options.clientSlug.charAt(0).toUpperCase() + options.clientSlug.slice(1) : "Client");

  // Generate the full written narrative report (replaces emoji metric lines)
  const narrative = await generateNarrative(allMetrics, period, displayName);

  // Audit
  await logQueryAudit(
    {
      user_id: options.userId,
      channel_id: options.channelId,
      client_slug: options.clientSlug,
      prompt: `[Diagnostic Report] ${period.label}`,
      sql_executed: "[multi-query diagnostic report]",
      table_used: "fact_kpi_daily, fact_spend_daily, google_account_performance_report, meta_customaccount_insights_daily",
      row_count: allMetrics.length,
    },
    options.clientSlug,
  );

  return narrative;
}
