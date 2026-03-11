/**
 * experiment_agent.ts — GeoLift experiment management from Slack.
 * Handles /geolift slash command: run, status, results, list, help.
 * Also responds to natural-language experiment questions in channel messages.
 */

import OpenAI from "openai";
import { runReadOnlyQuery, logQueryAudit, getSupabase } from "./db";

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
  sections.push("");

  // Lift summary
  const liftSign = avgLift >= 0 ? "+" : "";
  sections.push(`*Cumulative revenue lift:* ${liftSign}$${Math.abs(totalLift).toLocaleString("en-US", { maximumFractionDigits: 0 })}`);
  sections.push(`*Average daily lift:* ${liftSign}$${Math.abs(avgLift).toLocaleString("en-US", { maximumFractionDigits: 0 })}`);

  // Confidence interval
  if (avgLower !== null && avgUpper !== null) {
    const lowerSign = avgLower >= 0 ? "+" : "";
    const upperSign = avgUpper >= 0 ? "+" : "";
    sections.push(`*90% CI (daily):* [${lowerSign}$${Math.abs(avgLower).toLocaleString("en-US", { maximumFractionDigits: 0 })}, ${upperSign}$${Math.abs(avgUpper).toLocaleString("en-US", { maximumFractionDigits: 0 })}]`);

    // Significance check: is zero outside the interval?
    const significant = (avgLower > 0 && avgUpper > 0) || (avgLower < 0 && avgUpper < 0);
    if (significant) {
      const direction = avgLift > 0 ? "positive" : "negative";
      sections.push(`:white_check_mark: *Statistically significant* at 90% confidence. The effect is ${direction}.`);
    } else {
      sections.push(`:grey_question: *Not statistically significant* at 90% confidence. The confidence interval includes zero.`);
    }
  }

  // Plain-language interpretation
  sections.push("");
  if (totalLift > 0 && avgLower !== null && avgLower > 0) {
    sections.push(`:bulb: *Interpretation:* The treatment geos (${treatment}) showed a meaningful revenue increase compared to holdout geos (${holdout}). This suggests the intervention had a real positive impact.`);
  } else if (totalLift > 0) {
    sections.push(`:bulb: *Interpretation:* The treatment geos (${treatment}) showed higher revenue than holdout geos (${holdout}), but the result is not statistically conclusive. Consider running a longer test or using more geos.`);
  } else if (totalLift < 0 && avgUpper !== null && avgUpper < 0) {
    sections.push(`:bulb: *Interpretation:* The treatment geos (${treatment}) showed a revenue *decrease* compared to holdout geos (${holdout}). This may indicate the intervention had a negative effect.`);
  } else {
    sections.push(`:bulb: *Interpretation:* No clear effect detected. The intervention may have had no impact, or the test may need more statistical power (more geos or longer duration).`);
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
  options: { userId?: string; channelId?: string; clientSlug?: string }
): Promise<string> {
  const lower = prompt.toLowerCase();

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

  // LLM-powered guidance for open-ended experiment questions
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return `I can help with GeoLift experiments. Try:
- \`/geolift run <slug> <start> <end> treatment=<geos> holdout=<geos>\` to create a test
- \`/geolift list\` to see recent experiments
- \`/geolift help\` for full command reference`;
  }

  try {
    const client = new OpenAI({ apiKey });
    const response = await client.chat.completions.create({
      model: process.env.OPENAI_MODEL || "gpt-4o-mini",
      messages: [
        {
          role: "system",
          content: `You are a measurement science expert helping with GeoLift geo-based incrementality tests.
The platform uses Facebook's GeoLift package. Users can run experiments via /geolift commands.

Available commands:
- /geolift run <slug> <start> <end> treatment=TX,CA holdout=NY,FL
- /geolift status <slug>
- /geolift results <slug>
- /geolift list
- /geolift check-geos <start> <end>

Database has: experiments, experiment_results, fact_kpi_geo_daily (report_date, geo_id, revenue, orders), dim_geo (geo_id, geo_name).

Give concise, practical guidance. If the user wants to run a test, suggest the exact /geolift command. Keep responses under 300 words.`,
        },
        { role: "user", content: prompt },
      ],
      temperature: 0.3,
      max_tokens: 500,
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
