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

  // Revenue & Orders
  const kpiSql = `
    SELECT
      ${periodCase(dc, p, "SUM", "revenue", "revenue")},
      ${periodCase(dc, p, "SUM", "orders", "orders")}
    FROM public_marts.fact_kpi_daily
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

  const sql = `
    SELECT
      ${periodCase(dc, p, "SUM", "metrics_cost_micros::numeric / 1000000", "spend")},
      ${periodCase(dc, p, "SUM", "metrics_conversions_value::numeric", "conv_value")},
      ${periodCase(dc, p, "SUM", "metrics_conversions::numeric", "conversions")},
      ${periodCase(dc, p, "SUM", "metrics_impressions::numeric", "impressions")},
      ${periodCase(dc, p, "SUM", "metrics_clicks::numeric", "clicks")}
    FROM raw.google_account_performance_report
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

  const sql = `
    SELECT
      ${periodCase(dc, p, "SUM", "spend::numeric", "spend")},
      ${periodCase(dc, p, "SUM", "impressions::numeric", "impressions")},
      ${periodCase(dc, p, "SUM", "inline_link_clicks::numeric", "clicks")},
      ${periodCase(dc, p, "SUM", "unique_inline_link_clicks::numeric", "unique_clicks")},
      ${periodCase(dc, p, "AVG", "frequency::numeric", "frequency")}
    FROM raw.meta_ads_insights
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

  return metrics;
}

/**
 * Try to pull Meta ROAS from raw table.
 * Meta Ads Insights may have a `purchase_roas` column depending on Airbyte config.
 * Fails gracefully if the column doesn't exist.
 */
async function pullMetaROAS(p: PeriodParams, clientSlug?: string): Promise<Metric[]> {
  const dc = "date_start::date";

  // Attempt 1: purchase_roas column (some Airbyte configs flatten this)
  const sql1 = `
    SELECT
      ${periodCase(dc, p, "AVG", "purchase_roas::numeric", "roas")}
    FROM raw.meta_ads_insights
    WHERE purchase_roas IS NOT NULL
  `;
  const { data: d1, error: e1 } = await runReadOnlyQuery(sql1, clientSlug);
  if (!e1 && d1?.length) {
    const r = d1[0] as Record<string, unknown>;
    const curR = num(r, "cur_roas"), priR = num(r, "pri_roas");
    if (curR > 0 || priR > 0) {
      return [metric("Meta ROAS", curR, priR, "roas", "up-good", "meta")];
    }
  }

  // Attempt 2: calculate from action_values JSON (common Airbyte format)
  // action_values is a JSONB array: [{"action_type":"omni_purchase","value":"123.45"},...]
  const sql2 = `
    SELECT
      SUM(CASE
        WHEN ${dc} >= '${p.currentStart}' AND ${dc} < '${p.currentEnd}'
        THEN (SELECT SUM((elem->>'value')::numeric)
              FROM jsonb_array_elements(action_values::jsonb) AS elem
              WHERE elem->>'action_type' LIKE '%purchase%')
        ELSE 0 END) as cur_purchase_value,
      SUM(CASE
        WHEN ${dc} >= '${p.priorStart}' AND ${dc} < '${p.priorEnd}'
        THEN (SELECT SUM((elem->>'value')::numeric)
              FROM jsonb_array_elements(action_values::jsonb) AS elem
              WHERE elem->>'action_type' LIKE '%purchase%')
        ELSE 0 END) as pri_purchase_value,
      SUM(CASE WHEN ${dc} >= '${p.currentStart}' AND ${dc} < '${p.currentEnd}' THEN spend::numeric ELSE 0 END) as cur_spend,
      SUM(CASE WHEN ${dc} >= '${p.priorStart}' AND ${dc} < '${p.priorEnd}' THEN spend::numeric ELSE 0 END) as pri_spend
    FROM raw.meta_ads_insights
    WHERE action_values IS NOT NULL
  `;
  const { data: d2, error: e2 } = await runReadOnlyQuery(sql2, clientSlug);
  if (!e2 && d2?.length) {
    const r = d2[0] as Record<string, unknown>;
    const curPV = num(r, "cur_purchase_value"), priPV = num(r, "pri_purchase_value");
    const curS = num(r, "cur_spend"), priS = num(r, "pri_spend");
    if (curPV > 0 || priPV > 0) {
      return [metric("Meta ROAS", curS > 0 ? curPV / curS : 0, priS > 0 ? priPV / priS : 0, "roas", "up-good", "meta")];
    }
  }

  // No Meta ROAS data available — that's OK, the overall MER covers blended ROAS
  return [];
}

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

  const sysPrompt = `You are an expert performance marketing analyst writing a monthly diagnostic report for an e-commerce brand.

Your job:
1. Summarize overall performance in 2–3 sentences.
2. Identify the biggest movers and explain WHY they likely changed using cause-and-effect reasoning from the metrics.
3. Call out concerning trends or standout wins.
4. Provide 3–5 specific, actionable strategy recommendations.

Diagnostic reasoning patterns:
- ROAS dropped + CPC increased + CTR dropped → ad relevance declining, likely creative fatigue
- CTR dropped + frequency increased → audience saturation, too many impressions per user
- Conversions dropped + clicks stable → landing page or checkout issue
- Impressions increased + CTR dropped → audience expansion diluting quality
- CPA increased + conversion rate dropped → either traffic quality or offer/landing page issue
- If Meta frequency > 2.5, flag creative fatigue and recommend new creatives
- If Google CVR dropped but clicks increased, check for keyword quality issues

Rules:
- Be concise and direct, no fluff or filler.
- Support every claim with data.
- Strategy recommendations must be specific: "Launch 3–5 new Meta ad creatives to combat frequency of X.X" not "improve ads".
- Keep the entire response under 350 words.
- Do NOT use emoji — the metric lines already have emoji.
- Write in plain text, not markdown (no **, no ##, no bullets).
- Use short paragraphs separated by blank lines.`;

  const userPrompt = `Monthly performance data — ${period.label}:

${metricLines}

BIGGEST MOVERS (>5% change): ${sigLines}

Write the diagnostic analysis and strategy recommendations.`;

  try {
    const client = new OpenAI({ apiKey });
    const res = await client.chat.completions.create({
      model: process.env.OPENAI_MODEL || "gpt-5.4",
      messages: [
        { role: "system", content: sysPrompt },
        { role: "user", content: userPrompt },
      ],
      temperature: 0.3,
      max_tokens: 900,
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
    "full report",
    "channel report",
    "how did",
    "how were",
    "how was",
    "report for",
  ];
  return phrases.some((p) => lower.includes(p));
}

/**
 * Generate a full diagnostic report with metric breakdowns and AI analysis.
 */
export async function generateDiagnosticReport(
  prompt: string,
  options: { userId?: string; channelId?: string; clientSlug?: string },
): Promise<string> {
  const period = parseReportPeriod(prompt);

  // Pull all metric groups in parallel
  const [overallMetrics, googleMetrics, metaMetrics, metaROAS] = await Promise.all([
    pullOverallKPIs(period, options.clientSlug),
    pullGoogleMetrics(period, options.clientSlug),
    pullMetaMetrics(period, options.clientSlug),
    pullMetaROAS(period, options.clientSlug),
  ]);

  // Merge Meta ROAS into meta metrics (insert after Meta Spend if available)
  const mergedMeta = [...metaMetrics];
  if (metaROAS.length > 0) {
    const spendIdx = mergedMeta.findIndex((m) => m.name === "Meta Spend");
    mergedMeta.splice(spendIdx + 1, 0, ...metaROAS);
  }

  const allMetrics = [...overallMetrics, ...googleMetrics, ...mergedMeta];

  if (allMetrics.length === 0) {
    return "No data available for the requested period. Verify that `fact_kpi_daily` and `fact_spend_daily` have data.";
  }

  // ── Build the formatted report ──
  const sections: string[] = [];
  sections.push(`*📊 Diagnostic Report — ${period.label}*\n`);

  // Overall KPIs
  const overall = allMetrics.filter((m) => m.section === "overall");
  if (overall.length) {
    sections.push("*── Overall Performance ──*");
    sections.push(overall.map(fmtMetric).join("\n"));
  }

  // Google Ads
  const google = allMetrics.filter((m) => m.section === "google");
  if (google.length) {
    sections.push("\n*── Google Ads ──*");
    sections.push(google.map(fmtMetric).join("\n"));
  }

  // Meta (Facebook / Instagram)
  const meta = allMetrics.filter((m) => m.section === "meta");
  if (meta.length) {
    sections.push("\n*── Meta (Facebook / Instagram) ──*");
    sections.push(meta.map(fmtMetric).join("\n"));
  }

  // AI narrative analysis
  const narrative = await generateNarrative(allMetrics, period);
  sections.push("\n*── Analysis & Strategy ──*");
  sections.push(narrative);

  // Audit
  await logQueryAudit(
    {
      user_id: options.userId,
      channel_id: options.channelId,
      client_slug: options.clientSlug,
      prompt: `[Diagnostic Report] ${period.label}`,
      sql_executed: "[multi-query diagnostic report]",
      table_used: "fact_kpi_daily, fact_spend_daily, google_account_performance_report, meta_ads_insights",
      row_count: allMetrics.length,
    },
    options.clientSlug,
  );

  return sections.join("\n");
}
