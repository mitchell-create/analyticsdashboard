/**
 * experiment_agent.ts — GeoLift experiment management from Slack.
 * Handles /geolift slash command: run, status, results, list, help.
 * Also responds to natural-language experiment questions in channel messages.
 */

import OpenAI from "openai";
import { spawn } from "child_process";
import * as path from "path";
import { runReadOnlyQuery, logQueryAudit, getSupabase } from "./db";
import type { ThreadMessage } from "./types";

// ─── Types ───────────────────────────────────────────────────────────────────

interface ExperimentRow {
  id: number;
  experiment_slug: string;
  experiment_type: string;
  start_date: string;
  end_date: string;
  config: { treatment_geos?: string[]; holdout_geos?: string[] };
  status: string;
  created_at: string;
}

interface ExperimentResult {
  result_date: string;
  metric: string;
  value: number | null;
  interval_lower: number | null;
  interval_upper: number | null;
  metadata: unknown;
}

interface ValidationError {
  field: string;
  message: string;
}

interface ParsedRunCommand {
  slug: string;
  startDate: string;
  endDate: string;
  treatmentGeos: string[];
  holdoutGeos: string[];
}

interface AnalysisRequest {
  treatmentGeos: string[];
  holdoutGeos: string[];
  testStartDate: string;     // when treatment began (YYYY-MM-DD)
  testEndDate: string;       // when treatment ended (YYYY-MM-DD)
  campaignInfo?: string;     // optional label (campaign name/ID)
  experimentSlug: string;    // auto-generated from params
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const GEO_RE = /^[A-Z]{2}$/;
const MIN_DAYS = 14;
const MAX_DAYS = 365;

const HELP_TEXT = `*GeoLift Experiment Agent*

*Commands:*
\`/geolift run <slug> <start> <end> treatment=<geos> holdout=<geos>\`
  Create and queue a GeoLift incrementality test.
  Example: \`/geolift run q1-texas 2025-01-01 2025-03-31 treatment=TX,CA holdout=NY,FL,OH\`

\`/geolift status <slug>\`
  Check experiment status.

\`/geolift results <slug>\`
  View results with plain-language interpretation.

\`/geolift list\`
  List recent experiments.

\`/geolift check-geos <start> <end>\`
  Show which geos have data in the date range.

\`/geolift help\`
  Show this help message.

*Tips:*
- Geos use 2-letter state codes (TX, CA, NY, etc.)
- Date range should be at least 14 days
- Treatment and holdout geos must not overlap
- You can also ask naturally: "run a geolift test for Texas and California"`;

// ─── Parsing ─────────────────────────────────────────────────────────────────

function parseRunCommand(text: string): ParsedRunCommand | string {
  // /geolift run <slug> <start> <end> treatment=TX,CA holdout=NY,FL
  const parts = text.trim().split(/\s+/);
  if (parts.length < 5) {
    return "Usage: `/geolift run <slug> <start_date> <end_date> treatment=<geos> holdout=<geos>`";
  }

  const slug = parts[0];
  const startDate = parts[1];
  const endDate = parts[2];

  let treatmentGeos: string[] = [];
  let holdoutGeos: string[] = [];

  for (const part of parts.slice(3)) {
    const lower = part.toLowerCase();
    if (lower.startsWith("treatment=")) {
      treatmentGeos = part.substring("treatment=".length).toUpperCase().split(",").filter(Boolean);
    } else if (lower.startsWith("holdout=")) {
      holdoutGeos = part.substring("holdout=".length).toUpperCase().split(",").filter(Boolean);
    }
  }

  return { slug, startDate, endDate, treatmentGeos, holdoutGeos };
}

// ─── Validation ──────────────────────────────────────────────────────────────

async function validateRunParams(params: ParsedRunCommand, clientSlug?: string): Promise<ValidationError[]> {
  const errors: ValidationError[] = [];

  // Slug format
  if (!/^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/.test(params.slug)) {
    errors.push({ field: "slug", message: "Slug must be lowercase alphanumeric with hyphens, 3-50 chars (e.g. `q1-texas-test`)" });
  }

  // Date format
  if (!DATE_RE.test(params.startDate)) {
    errors.push({ field: "start_date", message: `Invalid start date format: \`${params.startDate}\`. Use YYYY-MM-DD.` });
  }
  if (!DATE_RE.test(params.endDate)) {
    errors.push({ field: "end_date", message: `Invalid end date format: \`${params.endDate}\`. Use YYYY-MM-DD.` });
  }

  if (DATE_RE.test(params.startDate) && DATE_RE.test(params.endDate)) {
    const start = new Date(params.startDate);
    const end = new Date(params.endDate);
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    if (start >= end) {
      errors.push({ field: "dates", message: "Start date must be before end date." });
    }

    const diffDays = Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));
    if (diffDays < MIN_DAYS) {
      errors.push({ field: "dates", message: `Date range must be at least ${MIN_DAYS} days (got ${diffDays}).` });
    }
    if (diffDays > MAX_DAYS) {
      errors.push({ field: "dates", message: `Date range exceeds ${MAX_DAYS} days (got ${diffDays}).` });
    }

    if (end > today) {
      errors.push({ field: "end_date", message: "End date cannot be in the future." });
    }
  }

  // Geos
  if (params.treatmentGeos.length === 0) {
    errors.push({ field: "treatment", message: "At least 1 treatment geo required. Use `treatment=TX,CA`." });
  }
  if (params.holdoutGeos.length === 0) {
    errors.push({ field: "holdout", message: "At least 1 holdout geo required. Use `holdout=NY,FL`." });
  }

  for (const geo of [...params.treatmentGeos, ...params.holdoutGeos]) {
    if (!GEO_RE.test(geo)) {
      errors.push({ field: "geos", message: `Invalid geo code: \`${geo}\`. Use 2-letter state codes (TX, CA, NY).` });
    }
  }

  // Overlap check
  const overlap = params.treatmentGeos.filter((g) => params.holdoutGeos.includes(g));
  if (overlap.length > 0) {
    errors.push({ field: "geos", message: `Geos cannot be in both treatment and holdout: ${overlap.join(", ")}` });
  }

  // If basic validation passes, check DB
  if (errors.length === 0) {
    await validateGeosExist(params, errors, clientSlug);
    await validateGeoDataCoverage(params, errors, clientSlug);
    await validateSlugUnique(params.slug, errors, clientSlug);
  }

  return errors;
}

async function validateGeosExist(params: ParsedRunCommand, errors: ValidationError[], clientSlug?: string): Promise<void> {
  const allGeos = [...new Set([...params.treatmentGeos, ...params.holdoutGeos])];
  const quotedGeos = allGeos.map((g) => `'${g}'`).join(",");
  const sql = `SELECT geo_id FROM public_marts.dim_geo WHERE geo_id IN (${quotedGeos})`;
  const { data } = await runReadOnlyQuery(sql, clientSlug);
  const found = new Set((data as { geo_id: string }[]).map((r) => r.geo_id));
  const missing = allGeos.filter((g) => !found.has(g));
  if (missing.length > 0) {
    errors.push({ field: "geos", message: `Geos not found in dim_geo: ${missing.join(", ")}` });
  }
}

async function validateGeoDataCoverage(params: ParsedRunCommand, errors: ValidationError[], clientSlug?: string): Promise<void> {
  const allGeos = [...new Set([...params.treatmentGeos, ...params.holdoutGeos])];
  const quotedGeos = allGeos.map((g) => `'${g}'`).join(",");
  const sql = `
    SELECT geo_id, COUNT(*) as day_count, MIN(report_date) as first_date, MAX(report_date) as last_date
    FROM public_marts.fact_kpi_geo_daily
    WHERE geo_id IN (${quotedGeos})
      AND report_date >= '${params.startDate}' AND report_date <= '${params.endDate}'
    GROUP BY geo_id
  `;
  const { data } = await runReadOnlyQuery(sql, clientSlug);
  const coverage = new Map((data as { geo_id: string; day_count: string }[]).map((r) => [r.geo_id, parseInt(r.day_count, 10)]));
  const noData = allGeos.filter((g) => !coverage.has(g));
  if (noData.length > 0) {
    errors.push({ field: "geos", message: `No data in date range for geos: ${noData.join(", ")}` });
  }
  const sparse = allGeos.filter((g) => {
    const count = coverage.get(g);
    return count !== undefined && count < MIN_DAYS;
  });
  if (sparse.length > 0) {
    errors.push({ field: "geos", message: `Sparse data (< ${MIN_DAYS} days) for geos: ${sparse.join(", ")}` });
  }
}

async function validateSlugUnique(slug: string, errors: ValidationError[], clientSlug?: string): Promise<void> {
  const sql = `SELECT experiment_slug, status FROM public.experiments WHERE experiment_slug = '${slug.replace(/'/g, "''")}'`;
  const { data } = await runReadOnlyQuery(sql, clientSlug);
  if (Array.isArray(data) && data.length > 0) {
    const existing = data[0] as { status: string };
    errors.push({
      field: "slug",
      message: `Experiment \`${slug}\` already exists (status: ${existing.status}). Use a different slug or check status with \`/geolift status ${slug}\`.`,
    });
  }
}

// ─── Queue Experiment ────────────────────────────────────────────────────────

async function queueExperiment(params: ParsedRunCommand, clientSlug?: string): Promise<{ id: number } | string> {
  const supabase = getSupabase(clientSlug);
  if (!supabase) return "Supabase not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY.";

  const row = {
    experiment_slug: params.slug,
    experiment_type: "geolift",
    start_date: params.startDate,
    end_date: params.endDate,
    config: {
      treatment_geos: params.treatmentGeos,
      holdout_geos: params.holdoutGeos,
    },
    status: "queued",
  };

  const { data, error } = await supabase.from("experiments").upsert(row, { onConflict: "experiment_slug" }).select("id").single();
  if (error) return `Failed to queue experiment: ${error.message}`;
  return { id: data.id };
}

// ─── Fetch Experiment ────────────────────────────────────────────────────────

async function fetchExperiment(slug: string, clientSlug?: string): Promise<ExperimentRow | null> {
  const sql = `SELECT id, experiment_slug, experiment_type, start_date::text, end_date::text, config, status, created_at::text FROM public.experiments WHERE experiment_slug = '${slug.replace(/'/g, "''")}'`;
  const { data } = await runReadOnlyQuery(sql, clientSlug);
  if (!Array.isArray(data) || data.length === 0) return null;
  return data[0] as ExperimentRow;
}

async function fetchExperimentResults(experimentId: number, clientSlug?: string): Promise<ExperimentResult[]> {
  const sql = `
    SELECT result_date::text, metric, value, interval_lower, interval_upper, metadata
    FROM public.experiment_results
    WHERE experiment_id = ${experimentId}
    ORDER BY result_date
  `;
  const { data } = await runReadOnlyQuery(sql, clientSlug);
  return (data || []) as ExperimentResult[];
}

async function fetchRecentExperiments(limit = 10, clientSlug?: string): Promise<ExperimentRow[]> {
  const sql = `
    SELECT id, experiment_slug, experiment_type, start_date::text, end_date::text, config, status, created_at::text
    FROM public.experiments
    ORDER BY created_at DESC
    LIMIT ${limit}
  `;
  const { data } = await runReadOnlyQuery(sql, clientSlug);
  return (data || []) as ExperimentRow[];
}

// ─── Results Interpretation ──────────────────────────────────────────────────

function interpretResults(experiment: ExperimentRow, results: ExperimentResult[]): string {
  if (results.length === 0) {
    return `:hourglass: Experiment \`${experiment.experiment_slug}\` has no results yet (status: ${experiment.status}).`;
  }

  const revenueResults = results.filter((r) => r.metric === "revenue" && r.value !== null);
  if (revenueResults.length === 0) {
    return `:warning: Experiment \`${experiment.experiment_slug}\` completed but produced no revenue lift data. The GeoLift model may need more data or different geo selections.`;
  }

  // Parse metadata from the first result row (contains estimator, p-value, etc.)
  // Metadata format: "estimator=geolift-scm,p_value=0.446,perc_lift=-19.3%,incremental=-14261.69,weights=fl:0.128|ma:0.656|wa:0.216"
  // OR JSONB: {"raw": "estimator=..."}
  let metaStr = "";
  const firstMeta = revenueResults[0]?.metadata;
  if (firstMeta) {
    if (typeof firstMeta === "string") {
      metaStr = firstMeta;
    } else if (typeof firstMeta === "object" && (firstMeta as Record<string, unknown>).raw) {
      metaStr = String((firstMeta as Record<string, unknown>).raw);
    }
  }

  const metaMap = new Map<string, string>();
  for (const part of metaStr.split(",")) {
    const [key, ...valParts] = part.split("=");
    if (key && valParts.length > 0) metaMap.set(key.trim(), valParts.join("=").trim());
  }

  const estimator = metaMap.get("estimator") || "unknown";
  const pValueStr = metaMap.get("p_value") || null;
  const percLiftStr = metaMap.get("perc_lift") || null;
  const incrementalStr = metaMap.get("incremental") || null;
  const isSCM = estimator.includes("geolift-scm") || estimator.includes("geolift");
  const isDiffInMeans = estimator.includes("difference-in-means");

  // Aggregate: average lift across all result dates
  const values = revenueResults.map((r) => r.value!);
  const lowers = revenueResults.filter((r) => r.interval_lower !== null).map((r) => r.interval_lower!);
  const uppers = revenueResults.filter((r) => r.interval_upper !== null).map((r) => r.interval_upper!);

  const totalLift = values.reduce((a, b) => a + b, 0);
  const avgLift = totalLift / values.length;
  const avgLower = lowers.length > 0 ? lowers.reduce((a, b) => a + b, 0) / lowers.length : null;
  const avgUpper = uppers.length > 0 ? uppers.reduce((a, b) => a + b, 0) / uppers.length : null;

  const config = experiment.config || {};
  const treatment = (config.treatment_geos || []).join(", ");
  const holdout = (config.holdout_geos || []).join(", ");

  const sections: string[] = [];

  // Header
  sections.push(`*:bar_chart: GeoLift Results: \`${experiment.experiment_slug}\`*`);
  sections.push(`Period: ${experiment.start_date} to ${experiment.end_date}`);
  sections.push(`Treatment geos: ${treatment}`);
  sections.push(`Holdout geos: ${holdout}`);
  sections.push(`Estimator: ${isSCM ? "Synthetic Control Method (GeoLift)" : isDiffInMeans ? "Difference-in-Means" : estimator}`);
  sections.push("");

  // Lift summary — use incremental from model if available, otherwise sum daily ATT
  const incrementalRevenue = incrementalStr ? parseFloat(incrementalStr) : totalLift;
  const liftSign = incrementalRevenue >= 0 ? "+" : "-";
  sections.push(`*Incremental revenue:* ${liftSign}$${Math.abs(incrementalRevenue).toLocaleString("en-US", { maximumFractionDigits: 0 })}`);

  if (percLiftStr && percLiftStr !== "NA%") {
    sections.push(`*Percent lift:* ${percLiftStr}`);
  }

  sections.push(`*Average daily lift:* ${avgLift >= 0 ? "+" : "-"}$${Math.abs(avgLift).toLocaleString("en-US", { maximumFractionDigits: 0 })}`);

  // P-value and significance
  const pValue = pValueStr && pValueStr !== "NA" ? parseFloat(pValueStr) : null;
  if (pValue !== null) {
    sections.push(`*P-value:* ${pValue.toFixed(4)}`);
    if (pValue <= 0.05) {
      sections.push(`:white_check_mark: *Statistically significant at 95% confidence* (p ≤ 0.05)`);
    } else if (pValue <= 0.10) {
      sections.push(`:white_check_mark: *Statistically significant at 90% confidence* (p ≤ 0.10)`);
    } else if (pValue <= 0.20) {
      sections.push(`:large_yellow_circle: *Marginally significant at 80% confidence* (p ≤ 0.20). Directionally suggestive but not conclusive.`);
    } else {
      sections.push(`:grey_question: *Not statistically significant* (p = ${pValue.toFixed(3)}). Cannot confidently attribute the observed difference to the intervention.`);
    }
  } else if (avgLower !== null && avgUpper !== null) {
    // Fallback: use CI for significance
    const significant = (avgLower > 0 && avgUpper > 0) || (avgLower < 0 && avgUpper < 0);
    if (significant) {
      const direction = avgLift > 0 ? "positive" : "negative";
      sections.push(`:white_check_mark: *Statistically significant* at 90% confidence. The effect is ${direction}.`);
    } else {
      sections.push(`:grey_question: *Not statistically significant* at 90% confidence. The confidence interval includes zero.`);
    }
  }

  // Confidence interval
  if (avgLower !== null && avgUpper !== null) {
    const fmtNum = (n: number) => `${n >= 0 ? "+" : "-"}$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
    sections.push(`*90% CI (daily):* [${fmtNum(avgLower)}, ${fmtNum(avgUpper)}]`);
  }

  // Plain-language interpretation
  sections.push("");
  if (incrementalRevenue > 0 && pValue !== null && pValue <= 0.10) {
    sections.push(`:bulb: *Interpretation:* The treatment geos (${treatment}) showed a statistically significant revenue increase compared to the synthetic control built from holdout geos (${holdout}). The campaign likely drove real incremental revenue.`);
  } else if (incrementalRevenue > 0 && (pValue === null || pValue > 0.10)) {
    sections.push(`:bulb: *Interpretation:* The treatment geos (${treatment}) showed higher revenue than holdout geos (${holdout}), but the result is not statistically conclusive. Consider running a longer test or using more geos.`);
  } else if (incrementalRevenue < 0 && pValue !== null && pValue <= 0.10) {
    sections.push(`:bulb: *Interpretation:* The treatment geos (${treatment}) showed a statistically significant revenue *decrease* compared to holdout geos (${holdout}). This suggests the campaign may have had a negative effect.`);
  } else if (incrementalRevenue < 0) {
    sections.push(`:bulb: *Interpretation:* The treatment geos (${treatment}) showed lower revenue than holdout geos (${holdout}), but this is not statistically conclusive. The negative signal could be noise.`);
  } else {
    sections.push(`:bulb: *Interpretation:* No clear effect detected. The intervention may have had no impact, or the test may need more statistical power (more geos or longer duration).`);
  }

  // Note on estimator
  if (isDiffInMeans) {
    sections.push(`\n:information_source: _Note: GeoLift Synthetic Control model was unavailable. Results use a simpler difference-in-means estimator, which is less precise._`);
  }

  // Daily summary table (last 7 rows or all if fewer)
  const recent = revenueResults.slice(-7);
  if (recent.length > 0) {
    sections.push("");
    sections.push("*Recent daily lift:*");
    const header = "Date | Lift | Lower | Upper";
    const rows = recent.map((r) => {
      const v = r.value !== null ? `$${r.value.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "—";
      const lo = r.interval_lower !== null ? `$${r.interval_lower.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "—";
      const hi = r.interval_upper !== null ? `$${r.interval_upper.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "—";
      return `${r.result_date} | ${v} | ${lo} | ${hi}`;
    });
    sections.push("```\n" + [header, ...rows].join("\n") + "\n```");
  }

  return sections.join("\n");
}

// ─── GeoLift Analysis (run R model from Slack) ─────────────────────────────

/**
 * Detect whether a message is requesting analysis of a completed test
 * (as opposed to asking for guidance on setting one up).
 */
export function isAnalysisRequest(text: string): boolean {
  const lower = text.toLowerCase();
  const hasAction = /\b(analyze|analyse|run.*analysis|run.*results|measure.*lift|check.*results|determine.*results|run.*through|run.*model)\b/.test(lower);
  const hasContext = /\b(treatment|holdout|ran|completed|test ran|results|i ran)\b/.test(lower);
  const hasDates = /\d{4}-\d{2}-\d{2}|\b(january|february|march|april|may|june|july|august|september|october|november|december)\b\s+\d{1,2}/i.test(lower);
  return hasAction && hasContext && hasDates;
}

/**
 * Use LLM to extract structured analysis parameters from conversational text.
 */
async function extractAnalysisParams(
  prompt: string,
  threadContext?: ThreadMessage[],
): Promise<AnalysisRequest | string> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) return "Analysis requires OPENAI_API_KEY.";

  const currentYear = new Date().getFullYear();
  const client = new OpenAI({ apiKey });

  const systemPrompt = `Extract GeoLift experiment parameters from the user's message and conversation history.
Return ONLY valid JSON with these fields:
{
  "treatment_geos": ["TX", "NC", "AZ"],
  "holdout_geos": ["FL", "WA", "MA"],
  "test_start_date": "2026-03-01",
  "test_end_date": "2026-03-28",
  "campaign_info": "Google brand search campaign 12345678"
}

Rules:
- Geos must be 2-letter US state codes, uppercase. Convert state names to codes (e.g. "Texas" → "TX", "California" → "CA").
- Dates must be YYYY-MM-DD format. If no year given, assume ${currentYear}.
- campaign_info is optional — extract if the user mentions a campaign name/ID/type.
- Look at the FULL conversation history, not just the last message — parameters may have been discussed earlier in the thread.
- If you cannot determine treatment_geos, holdout_geos, test_start_date, or test_end_date, return {"error": "description of what's missing"}.
- Return ONLY the JSON object, no markdown, no explanation.`;

  const messages: Array<{ role: "system" | "user" | "assistant"; content: string }> = [
    { role: "system", content: systemPrompt },
  ];
  if (threadContext && threadContext.length > 0) {
    for (const msg of threadContext) {
      messages.push({ role: msg.role, content: msg.content });
    }
  }
  messages.push({ role: "user", content: prompt });

  try {
    const response = await client.chat.completions.create({
      model: process.env.OPENAI_MODEL || "gpt-5.4",
      messages,
      temperature: 0,
      max_completion_tokens: 300,
    });

    const content = response.choices[0]?.message?.content?.trim();
    if (!content) return "Could not parse experiment parameters from your message.";

    // Strip markdown code fences if present
    const jsonStr = content.replace(/^```(?:json)?\n?/i, "").replace(/\n?```$/i, "").trim();
    const parsed = JSON.parse(jsonStr);

    if (parsed.error) return parsed.error;

    const treatmentGeos = (parsed.treatment_geos || []).map((g: string) => g.toUpperCase());
    const holdoutGeos = (parsed.holdout_geos || []).map((g: string) => g.toUpperCase());
    const testStartDate = parsed.test_start_date;
    const testEndDate = parsed.test_end_date;

    if (!treatmentGeos.length) return "I couldn't determine the treatment geos. Please specify which states were in the treatment group.";
    if (!holdoutGeos.length) return "I couldn't determine the holdout geos. Please specify which states were in the control/holdout group.";
    if (!testStartDate) return "I couldn't determine the test start date. Please specify when the test began (e.g., March 1 2026).";
    if (!testEndDate) return "I couldn't determine the test end date. Please specify when the test ended (e.g., March 28 2026).";

    // Generate slug from params
    const slugDate = testStartDate.replace(/-/g, "");
    const geoLabel = treatmentGeos.slice(0, 3).join("").toLowerCase();
    const experimentSlug = `geolift-${geoLabel}-${slugDate}`;

    return {
      treatmentGeos,
      holdoutGeos,
      testStartDate,
      testEndDate,
      campaignInfo: parsed.campaign_info || undefined,
      experimentSlug,
    };
  } catch (e) {
    return `Failed to parse parameters: ${e instanceof Error ? e.message : String(e)}`;
  }
}

/**
 * Spawn the Python model runner as a child process and wait for completion.
 */
async function runAnalysis(
  params: AnalysisRequest,
  options: { userId?: string; channelId?: string; clientSlug?: string },
): Promise<{ experimentId: number; slug: string } | string> {
  // Calculate pre-period: need at least 3x treatment period of pre-data (min 60 days)
  const testStart = new Date(params.testStartDate);
  const testEnd = new Date(params.testEndDate);
  const testDays = Math.round((testEnd.getTime() - testStart.getTime()) / (1000 * 60 * 60 * 24));
  const prePeriodDays = Math.max(testDays * 3, 60);
  const dataStartDate = new Date(testStart.getTime() - prePeriodDays * 86400000);
  const dataStart = dataStartDate.toISOString().slice(0, 10);
  const dataEnd = params.testEndDate;

  // Validate geos and data coverage using existing validation functions
  const validationParams: ParsedRunCommand = {
    slug: params.experimentSlug,
    startDate: dataStart,
    endDate: dataEnd,
    treatmentGeos: params.treatmentGeos,
    holdoutGeos: params.holdoutGeos,
  };
  const errors = await validateRunParams(validationParams, options.clientSlug);
  // Filter out slug uniqueness errors (allow re-runs of same analysis)
  const realErrors = errors.filter((e) => e.field !== "slug");
  if (realErrors.length > 0) {
    return `:x: Validation failed:\n${realErrors.map((e) => `- ${e.message}`).join("\n")}`;
  }

  // Upsert experiment row
  const supabase = getSupabase(options.clientSlug);
  if (!supabase) return "Supabase not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY.";

  const row = {
    experiment_slug: params.experimentSlug,
    experiment_type: "geolift",
    start_date: dataStart,
    end_date: dataEnd,
    config: {
      treatment_geos: params.treatmentGeos,
      holdout_geos: params.holdoutGeos,
      treatment_start_date: params.testStartDate,
      campaign_info: params.campaignInfo,
    },
    status: "running",
  };

  const { data, error } = await supabase
    .from("experiments")
    .upsert(row, { onConflict: "experiment_slug" })
    .select("id")
    .single();
  if (error) return `Database error: ${error.message}`;
  const experimentId = data.id;

  // Spawn model runner as child process
  const modelRunnerDir = process.env.MODEL_RUNNER_DIR
    || path.resolve(__dirname, "..", "..", "model-runner", "src");
  const pythonCmd = process.env.PYTHON_CMD || "python";
  const args = [
    "runner.py", "geolift-compute",
    params.experimentSlug,
    dataStart,
    dataEnd,
    params.treatmentGeos.join(","),
    params.holdoutGeos.join(","),
    params.testStartDate,
  ];

  console.log(`[GeoLift] Spawning: ${pythonCmd} ${args.join(" ")} in ${modelRunnerDir}`);

  return new Promise((resolve) => {
    const proc = spawn(pythonCmd, args, {
      cwd: modelRunnerDir,
      env: { ...process.env },
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (chunk: Buffer) => { stdout += chunk.toString(); });
    proc.stderr.on("data", (chunk: Buffer) => { stderr += chunk.toString(); });

    // Timeout after 5 minutes
    const timeout = setTimeout(() => {
      proc.kill("SIGTERM");
      resolve("Analysis timed out after 5 minutes. The R model may need more time or the data may be too large.");
    }, 5 * 60 * 1000);

    proc.on("close", (code: number | null) => {
      clearTimeout(timeout);
      console.log(`[GeoLift] Model runner exited with code ${code}`);
      if (stderr) console.log(`[GeoLift] stderr: ${stderr}`);
      if (code === 0) {
        resolve({ experimentId, slug: params.experimentSlug });
      } else {
        // Extract last few lines of stderr for user-friendly error
        const errorLines = stderr.split("\n").filter(Boolean).slice(-3).join(" ");
        resolve(`Model runner failed (exit code ${code}): ${errorLines || "unknown error"}`);
      }
    });

    proc.on("error", (err: Error) => {
      clearTimeout(timeout);
      resolve(`Failed to start model runner: ${err.message}. Ensure Python is installed and accessible.`);
    });
  });
}

/**
 * Full orchestration: extract params → ack → run analysis → post results.
 */
async function handleAnalysisRequest(
  prompt: string,
  options: {
    userId?: string;
    channelId?: string;
    clientSlug?: string;
    threadContext?: ThreadMessage[];
    postUpdate?: (text: string) => Promise<void>;
  },
): Promise<string> {
  // 1. Extract parameters from conversational text via LLM
  const params = await extractAnalysisParams(prompt, options.threadContext);
  if (typeof params === "string") {
    return `:x: ${params}\n\nPlease provide: treatment states, holdout states, test start date, and test end date.`;
  }

  // 2. Build acknowledgment message
  const testDays = Math.round(
    (new Date(params.testEndDate).getTime() - new Date(params.testStartDate).getTime()) / 86400000,
  );
  const ackMessage = `:microscope: *Starting GeoLift Analysis*
*Treatment:* ${params.treatmentGeos.join(", ")}
*Holdout:* ${params.holdoutGeos.join(", ")}
*Test period:* ${params.testStartDate} to ${params.testEndDate} (${testDays} days)
${params.campaignInfo ? `*Campaign:* ${params.campaignInfo}\n` : ""}:hourglass_flowing_sand: Running the Synthetic Control model — this typically takes 1-3 minutes...`;

  // 3. If we have a postUpdate callback, send ack immediately and run async
  if (options.postUpdate) {
    await options.postUpdate(ackMessage);

    try {
      const result = await runAnalysis(params, options);
      if (typeof result === "string") {
        await options.postUpdate(`:x: Analysis failed:\n${result}`);
        return "";
      }

      // Fetch and format results
      const exp = await fetchExperiment(result.slug, options.clientSlug);
      if (!exp) {
        await options.postUpdate(":x: Experiment completed but could not fetch results from database.");
        return "";
      }
      const results = await fetchExperimentResults(result.experimentId, options.clientSlug);
      const formatted = interpretResults(exp, results);
      await options.postUpdate(formatted);
    } catch (e) {
      const err = e instanceof Error ? e.message : String(e);
      await options.postUpdate(`:x: Analysis error: ${err}`);
    }
    return ""; // already posted via postUpdate
  }

  // Synchronous fallback: block until done
  const result = await runAnalysis(params, options);
  if (typeof result === "string") {
    return `${ackMessage}\n\n:x: Analysis failed:\n${result}`;
  }

  const exp = await fetchExperiment(result.slug, options.clientSlug);
  if (!exp) return `${ackMessage}\n\n:x: Could not fetch results.`;
  const results = await fetchExperimentResults(result.experimentId, options.clientSlug);
  return `${ackMessage}\n\n${interpretResults(exp, results)}`;
}

// ─── Geo Coverage Check ─────────────────────────────────────────────────────

async function checkGeoCoverage(startDate: string, endDate: string, clientSlug?: string): Promise<string> {
  if (!DATE_RE.test(startDate) || !DATE_RE.test(endDate)) {
    return "Usage: `/geolift check-geos <start_date> <end_date>` (YYYY-MM-DD)";
  }

  const sql = `
    SELECT g.geo_id, g.geo_name, COUNT(f.report_date) as days_with_data,
           COALESCE(SUM(f.revenue), 0) as total_revenue,
           COALESCE(SUM(f.orders), 0) as total_orders
    FROM public_marts.dim_geo g
    LEFT JOIN public_marts.fact_kpi_geo_daily f
      ON g.geo_id = f.geo_id
      AND f.report_date >= '${startDate}' AND f.report_date <= '${endDate}'
    GROUP BY g.geo_id, g.geo_name
    ORDER BY total_revenue DESC
  `;

  const { data, error } = await runReadOnlyQuery(sql, clientSlug);
  if (error) return `Error checking geos: ${error.message}`;
  if (!Array.isArray(data) || data.length === 0) return "No geos found in dim_geo.";

  const rows = data as { geo_id: string; geo_name: string; days_with_data: string; total_revenue: string; total_orders: string }[];
  const withData = rows.filter((r) => parseInt(r.days_with_data, 10) > 0);
  const noData = rows.filter((r) => parseInt(r.days_with_data, 10) === 0);

  const sections: string[] = [];
  sections.push(`*Geo coverage for ${startDate} to ${endDate}*`);
  sections.push(`${withData.length} geos with data, ${noData.length} without.\n`);

  if (withData.length > 0) {
    const header = "Geo | Name | Days | Revenue | Orders";
    const lines = withData.slice(0, 20).map((r) =>
      `${r.geo_id} | ${r.geo_name} | ${r.days_with_data} | $${Number(r.total_revenue).toLocaleString("en-US", { maximumFractionDigits: 0 })} | ${r.total_orders}`
    );
    sections.push("```\n" + [header, ...lines].join("\n") + "\n```");
  }

  if (noData.length > 0) {
    sections.push(`\n*Geos with no data:* ${noData.map((r) => r.geo_id).join(", ")}`);
  }

  return sections.join("\n");
}

// ─── Command Router ──────────────────────────────────────────────────────────

/**
 * Handle /geolift slash command. Returns text to post in Slack.
 */
export async function handleGeoliftCommand(
  text: string,
  options: { userId?: string; channelId?: string; clientSlug?: string }
): Promise<string> {
  const trimmed = text.trim();
  const parts = trimmed.split(/\s+/);
  const subcommand = parts[0]?.toLowerCase() || "help";

  try {
    switch (subcommand) {
      case "run":
        return await handleRun(parts.slice(1).join(" "), options);
      case "status":
        return await handleStatus(parts[1], options.clientSlug);
      case "results":
        return await handleResults(parts[1], options.clientSlug);
      case "list":
        return await handleList(options.clientSlug);
      case "check-geos":
        return await checkGeoCoverage(parts[1] || "", parts[2] || "", options.clientSlug);
      case "help":
      default:
        return HELP_TEXT;
    }
  } catch (e) {
    const err = e instanceof Error ? e.message : String(e);
    return `:x: Error: ${err}`;
  }
}

async function handleRun(text: string, options: { userId?: string; channelId?: string; clientSlug?: string }): Promise<string> {
  const parsed = parseRunCommand(text);
  if (typeof parsed === "string") return parsed;

  const errors = await validateRunParams(parsed, options.clientSlug);
  if (errors.length > 0) {
    const errorList = errors.map((e) => `- ${e.message}`).join("\n");
    return `:x: *Validation failed:*\n${errorList}`;
  }

  const result = await queueExperiment(parsed, options.clientSlug);
  if (typeof result === "string") return `:x: ${result}`;

  await logQueryAudit({
    user_id: options.userId,
    channel_id: options.channelId,
    client_slug: options.clientSlug,
    prompt: `[GeoLift] run ${parsed.slug}`,
    sql_executed: null,
    metadata: {
      experiment_id: result.id,
      slug: parsed.slug,
      treatment_geos: parsed.treatmentGeos,
      holdout_geos: parsed.holdoutGeos,
    },
  }, options.clientSlug);

  return `:white_check_mark: *Experiment queued!*

*Slug:* \`${parsed.slug}\`
*Type:* GeoLift (geo-based incrementality)
*Period:* ${parsed.startDate} to ${parsed.endDate}
*Treatment geos:* ${parsed.treatmentGeos.join(", ")}
*Holdout geos:* ${parsed.holdoutGeos.join(", ")}
*Status:* queued (ID: ${result.id})

The experiment will be picked up by the next Prefect worker run. Use \`/geolift status ${parsed.slug}\` to check progress.`;
}

async function handleStatus(slug: string | undefined, clientSlug?: string): Promise<string> {
  if (!slug) return "Usage: `/geolift status <experiment-slug>`";

  const exp = await fetchExperiment(slug, clientSlug);
  if (!exp) return `:grey_question: No experiment found with slug \`${slug}\`.`;

  const config = exp.config || {};
  const treatment = (config.treatment_geos || []).join(", ");
  const holdout = (config.holdout_geos || []).join(", ");

  const statusEmoji: Record<string, string> = {
    draft: ":memo:",
    queued: ":hourglass:",
    running: ":gear:",
    completed: ":white_check_mark:",
    failed: ":x:",
  };
  const emoji = statusEmoji[exp.status] || ":grey_question:";

  let text = `${emoji} *Experiment: \`${exp.experiment_slug}\`*

*Status:* ${exp.status}
*Type:* ${exp.experiment_type}
*Period:* ${exp.start_date} to ${exp.end_date}
*Treatment:* ${treatment || "—"}
*Holdout:* ${holdout || "—"}
*Created:* ${exp.created_at}`;

  if (exp.status === "completed") {
    text += `\n\nUse \`/geolift results ${slug}\` to see lift and confidence intervals.`;
  }

  return text;
}

async function handleResults(slug: string | undefined, clientSlug?: string): Promise<string> {
  if (!slug) return "Usage: `/geolift results <experiment-slug>`";

  const exp = await fetchExperiment(slug, clientSlug);
  if (!exp) return `:grey_question: No experiment found with slug \`${slug}\`.`;

  if (exp.status !== "completed" && exp.status !== "running") {
    return `:hourglass: Experiment \`${slug}\` has status \`${exp.status}\`. Results are available after the experiment completes.`;
  }

  const results = await fetchExperimentResults(exp.id, clientSlug);
  return interpretResults(exp, results);
}

async function handleList(clientSlug?: string): Promise<string> {
  const experiments = await fetchRecentExperiments(10, clientSlug);
  if (experiments.length === 0) return "No experiments found. Create one with `/geolift run`.";

  const statusEmoji: Record<string, string> = {
    draft: ":memo:",
    queued: ":hourglass:",
    running: ":gear:",
    completed: ":white_check_mark:",
    failed: ":x:",
  };

  const lines = experiments.map((exp) => {
    const emoji = statusEmoji[exp.status] || ":grey_question:";
    return `${emoji} \`${exp.experiment_slug}\` — ${exp.experiment_type} — ${exp.status} (${exp.start_date} to ${exp.end_date})`;
  });

  return `*Recent experiments:*\n${lines.join("\n")}`;
}

// ─── Natural Language Detection ──────────────────────────────────────────────

const EXPERIMENT_PATTERNS = [
  /\b(geolift|geo.?lift|geo.?test|incrementality|lift test|holdout test)\b/i,
  /\b(run|start|create|set up|setup)\b.*\b(experiment|test|geolift)\b/i,
  /\bexperiment\b.*\b(status|result|progress)\b/i,
  /\b(which|what)\b.*\bgeos?\b.*\b(have|data|available)\b/i,
  /\b(best practice|how to|guide|help)\b.*\b(geolift|holdout|treatment|experiment)\b/i,
  /\b(treatment|holdout)\b.*\b(region|geo|state|market)/i,
  /\b(region|geo|state|market)s?\b.*\b(treatment|holdout)\b/i,
  /\b(pick|choose|select|determine|decide)\b.*\b(region|geo|state|market|treatment|holdout)\b/i,
  /\b(similar|comparable)\b.*\b(region|geo|state|market)\b/i,
  /\bincremental\s*(lift|value|impact|result)/i,
  /\bbrand\s+search\b.*\b(lift|test|experiment|incremental)/i,
  /\b(analyze|analyse|run.*analysis|run.*results|measure.*lift|run.*through.*model)\b/i,
  /\bi ran\b.*\b(test|experiment|geolift)\b/i,
];

/**
 * Returns true if the message likely relates to experiments/GeoLift.
 * Used by index.ts to route messages to the experiment agent vs analytics agent.
 */
export function isExperimentQuery(text: string): boolean {
  return EXPERIMENT_PATTERNS.some((re) => re.test(text));
}

/**
 * Handle a natural-language experiment question (from channel message, not slash command).
 * Uses LLM to understand intent and respond with guidance or data.
 */
export async function answerExperimentQuery(
  prompt: string,
  options: {
    userId?: string;
    channelId?: string;
    clientSlug?: string;
    threadContext?: ThreadMessage[];
    postUpdate?: (text: string) => Promise<void>;
  },
): Promise<string> {
  const lower = prompt.toLowerCase();

  // Check for analysis request (user wants to run the GeoLift model on completed test data)
  if (isAnalysisRequest(prompt)) {
    return await handleAnalysisRequest(prompt, options);
  }

  // Direct pattern matches for common queries
  if (/\b(status|progress)\b.*\b\w+[-]\w+/.test(lower)) {
    const slugMatch = prompt.match(/\b([a-z0-9][-a-z0-9]+[a-z0-9])\b/);
    if (slugMatch) {
      const exp = await fetchExperiment(slugMatch[1], options.clientSlug);
      if (exp) return await handleStatus(slugMatch[1], options.clientSlug);
    }
  }

  if (/\bresults?\b.*\b\w+[-]\w+/.test(lower)) {
    const slugMatch = prompt.match(/\b([a-z0-9][-a-z0-9]+[a-z0-9])\b/);
    if (slugMatch) {
      const exp = await fetchExperiment(slugMatch[1], options.clientSlug);
      if (exp) return await handleResults(slugMatch[1], options.clientSlug);
    }
  }

  if (/\b(list|show|recent)\b.*\bexperiment/i.test(lower)) {
    return await handleList(options.clientSlug);
  }

  if (/\b(which|what)\b.*\bgeos?\b.*\b(have|data|available)\b/i.test(lower)) {
    return await checkGeoCoverage(
      new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10),
      new Date().toISOString().slice(0, 10),
      options.clientSlug
    );
  }

  // Detect region-selection / treatment-holdout design questions — fetch geo data for context
  const isRegionQuestion = /\b(treatment|holdout|region|pick|choose|select|determine|decide|similar|comparable)\b/i.test(lower)
    && /\b(region|geo|state|market|treatment|holdout)\b/i.test(lower);

  // LLM-powered guidance for open-ended experiment questions
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return `I can help with GeoLift experiments. Try:
- \`/geolift run <slug> <start> <end> treatment=<geos> holdout=<geos>\` to create a test
- \`/geolift list\` to see recent experiments
- \`/geolift help\` for full command reference`;
  }

  // If asking about regions, fetch the actual geo data to give data-informed recommendations
  let geoContext = "";
  if (isRegionQuestion) {
    try {
      const endDate = new Date().toISOString().slice(0, 10);
      const startDate = new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10);
      const geoSql = `
        SELECT g.geo_id, g.geo_name,
               COUNT(f.report_date) AS days_with_data,
               COALESCE(SUM(f.revenue)::numeric, 0) AS total_revenue,
               COALESCE(SUM(f.orders), 0) AS total_orders,
               COALESCE(ROUND(AVG(f.revenue)::numeric, 2), 0) AS avg_daily_revenue,
               COALESCE(ROUND(AVG(f.orders)::numeric, 1), 0) AS avg_daily_orders
        FROM public_marts.dim_geo g
        LEFT JOIN public_marts.fact_kpi_geo_daily f
          ON g.geo_id = f.geo_id
          AND f.report_date >= '${startDate}' AND f.report_date <= '${endDate}'
        GROUP BY g.geo_id, g.geo_name
        HAVING COUNT(f.report_date) > 0
        ORDER BY total_revenue DESC
      `;
      const { data } = await runReadOnlyQuery(geoSql, options.clientSlug);
      if (Array.isArray(data) && data.length > 0) {
        const rows = data as { geo_id: string; geo_name: string; days_with_data: string; total_revenue: string; total_orders: string; avg_daily_revenue: string; avg_daily_orders: string }[];
        const geoTable = rows.map(r =>
          `${r.geo_id} (${r.geo_name}): $${Number(r.total_revenue).toLocaleString("en-US", { maximumFractionDigits: 0 })} revenue, ${r.total_orders} orders, avg $${r.avg_daily_revenue}/day over ${r.days_with_data} days`
        ).join("\n");
        geoContext = `\n\nHere is the client's actual Shopify revenue data by state for the last 90 days (${startDate} to ${endDate}):\n${geoTable}\n\nUse this data to make specific, data-informed recommendations for treatment and holdout geo selection.`;
      }
    } catch (e) {
      // If geo query fails, continue without data context
    }
  }

  try {
    const client = new OpenAI({ apiKey });

    const systemContent = `You are a measurement science expert specializing in GeoLift geo-based incrementality testing. You have deep knowledge of Meta/Facebook's open-source GeoLift R package and geo experimentation methodology.

## PLATFORM COMMANDS
Users can run experiments via /geolift slash commands:
- /geolift run <slug> <start> <end> treatment=TX,CA holdout=NY,FL
- /geolift status <slug>
- /geolift results <slug>
- /geolift list
- /geolift check-geos <start> <end>

Database tables: experiments, experiment_results, fact_kpi_geo_daily (report_date, geo_id, revenue, orders), dim_geo (geo_id, geo_name).

## WHAT GEOLIFT IS
GeoLift measures the causal incremental effect of marketing campaigns at a geographic level using Synthetic Control Methods. It enables:
- Data-driven market selection for geo-tests using power calculators
- Statistical inference for measuring true incremental (causal) lift
- Privacy-safe measurement using aggregated data (no user-level tracking)

Geo experimentation works by administering treatment (e.g., running or pausing ad campaigns) at the geographic level — test regions receive the treatment while control regions do not. By comparing actual performance in test regions against a synthetic counterfactual built from control regions, you isolate the causal effect.

## STATISTICAL METHODOLOGY

### Synthetic Control Method (SCM)
1. Pre-Period Weighting: Identifies which control regions best replicate the test region's historical behavior
2. Counterfactual Construction: Assigns non-negative weights to control regions to create a "synthetic" version of the test region
3. Post-Period Gap: The difference between the observed test region outcome and the synthetic counterfactual = the causal treatment effect
4. Key Assumption: Control regions must be unaffected by treatment (no spillover), and regional patterns must remain stable

### Augmented Synthetic Control Methods (ASCM)
Standard SCM enhanced through prognostic functions to reduce bias and improve fit:
- Standard (no augmentation): Basic synthetic control
- Ridge (L2 regularization): Works well with <40 locations or <100 time points
- GSYN: Generalized synthetic control, better for larger panels
- "best" mode: Tests all three and selects lowest Scaled L2 Imbalance

### Statistical Inference
GeoLift uses conformal inference for p-values and confidence intervals. For each hypothesized effect size, it retrains the model and computes residuals to determine statistical significance.

P-value interpretation:
- p <= 0.05: Statistically significant at 95% confidence
- p <= 0.10: Significant at 90% confidence
- p <= 0.20: Significant at 80% confidence
- p > 0.20: Not statistically significant

## POWER ANALYSIS AND MARKET SELECTION

Power analysis is the critical pre-test step that determines:
- Optimal number of test locations
- Best test and control market combinations
- Minimum test duration needed
- Budget requirements
- Minimum Detectable Effect (MDE) — the smallest lift the test can reliably detect

### Selecting Markets — Key Criteria
- Low EffectSize (MDE): Can detect smaller effects = more sensitive test
- Low Scaled L2 Imbalance: Good pre-period fit between test and synthetic control (0 = perfect, <0.17 is strong)
- abs_lift_in_zero close to zero: No false positives when simulating 0% true effect
- High correlation (> 0.90) between test and synthetic control
- Appropriate ProportionTotal_Y: Test regions shouldn't contain too much or too little of total volume
- Reasonable Investment relative to available budget

### Treatment vs. Holdout (Control) Selection
- Treatment geos = where you CHANGE something (e.g., turn off brand search ads, increase spend). These are the test regions.
- Holdout geos = control regions where everything stays the same. They provide the baseline for comparison.
- Treatment and holdout geos should have SIMILAR historical revenue patterns and volume for valid statistical comparison.
- Avoid picking your top 1-2 revenue states as treatment — losing that revenue during the test is risky. Use mid-tier states instead.
- Need 2-5 geos in each group for statistical power.
- Ensure geographic distinctness — avoid nearby cities/states with spillover effects (e.g., if you pause ads in NJ, shoppers might see ads from NY campaigns).
- States with very low order volume won't provide useful signal.

## RUNNING A TEST

### Test Duration
- Run for at least 2-4 weeks to gather meaningful signal
- Include at least one complete purchase cycle for the product
- Pre-treatment data should be at least 4x the treatment period length (e.g., 90 days of pre-data for a 3-week test)
- Consider a cooldown period after the campaign ends

### During the Test
- Execute the campaign change ONLY in treatment markets for the predetermined duration
- Control markets must receive NO treatment changes
- Continue collecting outcome data (revenue, orders) in all markets
- Do NOT make other major campaign changes during the test period as it contaminates results

## INTERPRETING RESULTS

### Key Metrics
- Percent Lift: Relative increase in outcome vs. counterfactual (e.g., 5.4%)
- Incremental Y: Absolute additional units attributed to the campaign (e.g., 4,667 extra orders)
- ATT (Average Treatment Effect on Treated): Daily average incremental units
- P-value: Probability of observing this effect if the true effect was zero
- Confidence Interval: Range of plausible treatment effects

### Reading the Results
- Lift Plot: Shows observed test region vs. synthetic control over time. Pre-period lines should overlap closely (good fit). Post-period gap = campaign incrementality.
- ATT Plot: Shows daily treatment effect with confidence intervals. Pre-period values should center around zero. Post-period: large ATT with narrow CIs = high significance.
- Scaled L2 Imbalance: Pre-period fit quality. Score 0-1, lower is better. >83% improvement from naive is strong.

## BEST PRACTICES

### Pre-Test
1. Inspect data stability and structural similarities across regions before power analysis
2. Run power analysis with conservative budget estimates
3. Review the top 5 market candidates and compare power curves
4. Prefer test markets with high correlation (>0.90) and low abs_lift_in_zero
5. Ensure pre-treatment data is at least 4x the planned treatment period
6. Include at least one complete purchase cycle in the treatment period

### Test Design
1. Maintain geographic distinctness to avoid spillover
2. Document the CPIC (Cost Per Incremental Conversion) source
3. Verify treatment period aligns with actual campaign plans
4. Ensure sufficient control pool remains after selecting treatment markets

### Post-Test
1. Confirm no data anomalies during the test period
2. Check pre-period overlap quality in the Lift plot
3. Report both Percent Lift AND Incremental Y for stakeholder alignment
4. Use ATT plot confidence intervals to assess day-by-day significance

### Common Pitfalls
- Selecting too many test markets, exhausting the control pool
- Ignoring abs_lift_in_zero — nonzero values indicate false positive risk
- Not checking for spillover between nearby test and control markets
- Making other campaign changes during the test period (contaminates results)
- Using too short a test duration for the product's purchase cycle
- Running the test with states that have insufficient order volume

## MULTI-CELL TESTS
Multi-cell GeoLifts test multiple channels or strategies simultaneously across different regions. Use cases:
- Comparing incremental effects across two or more channels (e.g., Google brand search vs. Meta prospecting)
- Evaluating which strategy performs better
- Be conservative with cells — each cell reduces the control pool. With 40 cities, 2-3 cells is a prudent maximum.

## COMMUNICATION STYLE — CRITICAL RULES
You are chatting in Slack, not writing a blog post or textbook. Follow these rules strictly:

1. **Answer the specific question asked.** Do NOT repeat background info the user already knows. Do NOT restate what GeoLift is or how it works unless they specifically ask.
2. **Be conversational and direct.** Write like a smart colleague in Slack, not a formal report. Short paragraphs, plain language.
3. **NO giant numbered lists.** Do NOT structure every response as "Step 1, Step 2, Step 3..." with headers. Just answer naturally.
4. **NO "### Headers" formatting.** This is Slack, not a document. Use bold sparingly for emphasis only.
5. **Keep it short.** Aim for 150-250 words. Only go longer if the question genuinely requires detailed explanation.
6. **In follow-up messages in a thread**, be even more concise. The user already has context from earlier in the conversation. Just answer the new question directly.
7. **When suggesting geo groups**, present them simply (e.g., "Treatment: TX, NC, AZ / Holdout: FL, WA, MA") with brief reasoning — not a full table with every metric.
8. **When the user asks a practical "how do I" question**, give them the direct actionable answer first, then add brief context if needed. Don't bury the answer under paragraphs of setup.
9. **Never say "Here's a step-by-step approach" or "Follow these steps."** Just give the advice naturally.${geoContext}`;

    // Build multi-turn messages array with thread context
    const messages: Array<{ role: "system" | "user" | "assistant"; content: string }> = [
      { role: "system", content: systemContent },
    ];

    // Include prior thread messages for conversational continuity
    if (options.threadContext && options.threadContext.length > 0) {
      for (const msg of options.threadContext) {
        messages.push({ role: msg.role, content: msg.content });
      }
    }

    messages.push({ role: "user", content: prompt });

    const response = await client.chat.completions.create({
      model: process.env.OPENAI_MODEL || "gpt-5.4",
      messages,
      temperature: 0.3,
      max_completion_tokens: 1200,
    });

    return response.choices[0]?.message?.content?.trim() || "I couldn't generate guidance. Try `/geolift help` for available commands.";
  } catch (e) {
    return `I can help with GeoLift experiments. Try \`/geolift help\` for commands, or ask about experiment setup, holdout selection, or interpreting results.`;
  }
}

// ─── Results Polling (called by Prefect callback or periodic check) ──────────

/**
 * Check for recently completed experiments and return formatted results.
 * Can be called by a periodic job to post results back to Slack.
 */
export async function getNewlyCompletedResults(clientSlug?: string): Promise<{ slug: string; message: string }[]> {
  const sql = `
    SELECT id, experiment_slug, experiment_type, start_date::text, end_date::text, config, status, created_at::text
    FROM public.experiments
    WHERE status = 'completed'
      AND updated_at >= NOW() - INTERVAL '10 minutes'
    ORDER BY updated_at DESC
    LIMIT 5
  `;
  const { data } = await runReadOnlyQuery(sql, clientSlug);
  if (!Array.isArray(data) || data.length === 0) return [];

  const output: { slug: string; message: string }[] = [];
  for (const row of data as ExperimentRow[]) {
    const results = await fetchExperimentResults(row.id, clientSlug);
    const message = interpretResults(row, results);
    output.push({ slug: row.experiment_slug, message });
  }
  return output;
}
