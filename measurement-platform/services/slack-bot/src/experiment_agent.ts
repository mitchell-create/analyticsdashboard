/**
 * experiment_agent.ts — GeoLift & experiment setup assistant.
 * Uses OpenAI (gpt-4o) to guide users on GeoLift best practices and CausalImpact.
 * Can fetch current experiments from the DB for context.
 * Env: OPENAI_API_KEY, OPENAI_AGENT_MODEL (optional, defaults to gpt-4o)
 */

import OpenAI from "openai";
import { runReadOnlyQuery } from "./db";

// Use a capable model for reasoning (gpt-4o recommended for agent guidance)
const DEFAULT_AGENT_MODEL = "gpt-4o";

const GEOLIFT_BEST_PRACTICES = `
## GeoLift Best Practices (from facebookincubator/GeoLift)

**Data:**
- Use daily granularity (strongly recommended over weekly)
- Use highest geo granularity available (zip codes, cities, states)
- Have 4–5× the test duration of pre-campaign historical data (stable, no structural changes)
- Minimum: 25 pre-treatment periods, 20+ geo-units
- Historical data: 52+ weeks preferred (captures seasonality)
- Test duration: minimum 15 days (daily) or 4–6 weeks (weekly)
- No missing values for any unit or timestamp

**Test and Control Markets:**
- Match test and control markets on the same outcome (e.g. sales)
- Match on relevant variables: product distribution, seasonal variation

**Marketing:**
- Keep local marketing constant across test and control markets
- Account for local media (regional TV, offline)
- National media should be held constant to isolate Facebook/paid impact

**Repos:**
- GeoLift: https://github.com/facebookincubator/GeoLift
- CausalImpact (time-series): https://github.com/google/CausalImpact
`;

const SYSTEM_PROMPT = `You are an expert analytics assistant for a marketing measurement platform. You help users:
1. Set up and run GeoLift experiments (geo holdouts) and CausalImpact (time-series) tests
2. Understand best practices for incrementality testing
3. Interpret experiment results
4. Answer questions about their data (revenue, spend, orders, channels, experiments)

When discussing GeoLift:
- Reference the official repo: https://github.com/facebookincubator/GeoLift
- Installation: remotes::install_github("ebenmichael/augsynth") then remotes::install_github("facebookincubator/GeoLift")
- To run: \`python runner.py geolift <slug> <start> <end> <treatment_geos> <holdout_geos>\` (e.g. "my-test 2024-01-01 2024-02-28 TX,CA NY,FL")
- Data comes from fact_kpi_geo_daily (report_date, geo_id, revenue, orders)

When discussing CausalImpact:
- Use for pre/post intervention (e.g. campaign launch)
- Run: \`python runner.py causalimpact <slug> <start> <end> <intervention_date> [revenue|orders]\`

Best practices summary:
${GEOLIFT_BEST_PRACTICES}

If the user asks about their current experiments or data, use the CONTEXT block below. Be concise; Slack messages should be scannable. Use bullet points and short paragraphs.`;

async function fetchExperimentContext(clientSlug?: string): Promise<string> {
  const { data: exps } = await runReadOnlyQuery(`
    SELECT experiment_slug, experiment_type, start_date, end_date, status, config
    FROM public.experiments
    ORDER BY created_at DESC
    LIMIT 10
  `, clientSlug);
  if (!Array.isArray(exps) || exps.length === 0) {
    return "No experiments found in the database yet.";
  }
  const lines = (exps as Record<string, unknown>[]).map(
    (r) =>
      `- ${r.experiment_slug} (${r.experiment_type}): ${r.start_date} to ${r.end_date}, status=${r.status}`
  );
  return lines.join("\n");
}

async function fetchDataSummary(clientSlug?: string): Promise<string> {
  const { data: geo } = await runReadOnlyQuery(`
    SELECT COUNT(DISTINCT geo_id) AS geos, MIN(report_date) AS min_date, MAX(report_date) AS max_date
    FROM public_marts.fact_kpi_geo_daily WHERE revenue > 0 OR orders > 0
  `, clientSlug);
  const geoInfo =
    Array.isArray(geo) && geo.length > 0
      ? `fact_kpi_geo_daily: ${(geo[0] as Record<string, unknown>).geos} geos with data, ${(geo[0] as Record<string, unknown>).min_date} to ${(geo[0] as Record<string, unknown>).max_date}`
      : "fact_kpi_geo_daily: no geo data yet (or zeros).";
  return geoInfo;
}

export async function answerExperimentQuery(
  prompt: string,
  options?: { userId?: string; channelId?: string; clientSlug?: string }
): Promise<{ text: string; error?: string }> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return {
      text: "The experiment agent needs OPENAI_API_KEY in .env to help with GeoLift and experiment setup.",
    };
  }

  const model = process.env.OPENAI_AGENT_MODEL || DEFAULT_AGENT_MODEL;

  try {
    const [expContext, dataSummary] = await Promise.all([
      fetchExperimentContext(options?.clientSlug),
      fetchDataSummary(options?.clientSlug),
    ]);

    const contextBlock = `
CONTEXT (current state):
- Experiments: ${expContext}
- ${dataSummary}
`;

    const client = new OpenAI({ apiKey });
    const response = await client.chat.completions.create({
      model,
      messages: [
        { role: "system", content: SYSTEM_PROMPT + "\n\n" + contextBlock },
        { role: "user", content: prompt },
      ],
      temperature: 0.3,
      max_tokens: 1500,
    });

    const content = response.choices[0]?.message?.content?.trim();
    if (!content) {
      return { text: "I couldn't generate a response. Try rephrasing your question." };
    }

    return { text: content };
  } catch (err) {
    console.error("Experiment agent failed:", err);
    const msg = err instanceof Error ? err.message : String(err);
    return {
      text: `Experiment agent error: ${msg}. Check OPENAI_API_KEY and network.`,
      error: msg,
    };
  }
}

/** Detect if the user is asking about experiments, GeoLift setup, or best practices. */
export function isExperimentRequest(prompt: string): boolean {
  const lower = prompt.toLowerCase().trim();
  const triggers = [
    "geolift",
    "geo lift",
    "geo holdout",
    "geo test",
    "experiment setup",
    "experiment best practice",
    "how do i run",
    "how to run",
    "how do i set up",
    "how to set up",
    "incrementality",
    "causal impact",
    "causalimpact",
    "treatment geos",
    "holdout geos",
    "synthetic control",
    "market selection",
  ];
  return triggers.some((t) => lower.includes(t));
}
