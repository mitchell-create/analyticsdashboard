# GeoLift Slack Agent Specification

## Overview

Run GeoLift geo-based incrementality tests directly from Slack. Users issue `/geolift` commands (or mention the bot) to create, queue, and retrieve experiment results without leaving the channel.

---

## Architecture

```
Slack (/geolift command)
  |
  v
experiment_agent.ts (parse, validate, queue)
  |
  v
Supabase: experiments table (status = 'queued')
  |
  v
Prefect worker (run_experiments.py polls queued rows)
  |
  v
runner.py geolift -> geolift_runner.R (real GeoLift)
  |
  v
experiment_results table (lift, CI)
  |
  v
experiment_agent.ts polls & posts results back to Slack
```

---

## Database Schema

### experiments (public)

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| experiment_slug | text UNIQUE | e.g. `q1-texas-holdout` |
| experiment_type | text | `geolift` or `causal_impact` |
| start_date | date | |
| end_date | date | |
| config | jsonb | `{treatment_geos, holdout_geos}` |
| status | text | `draft`, `queued`, `running`, `completed`, `failed` |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### experiment_results (public)

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| experiment_id | int FK | references experiments(id) |
| result_date | date | |
| metric | text | e.g. `revenue` |
| value | numeric | point estimate of lift |
| interval_lower | numeric | lower 90% CI bound |
| interval_upper | numeric | upper 90% CI bound |
| metadata | jsonb | |

### fact_kpi_geo_daily (public_marts)

| Column | Type | Notes |
|--------|------|-------|
| report_date | date | |
| geo_id | text | state code (TX, CA, NY...) |
| revenue | numeric | |
| orders | integer | |

### dim_geo (public_marts)

| Column | Type | Notes |
|--------|------|-------|
| geo_id | text PK | |
| geo_name | text | Full state name |
| geo_type | text | `state` |

---

## Slack Commands

### `/geolift run`

Create and queue a GeoLift experiment.

**Syntax:**
```
/geolift run <slug> <start_date> <end_date> treatment=<geos> holdout=<geos>
```

**Example:**
```
/geolift run q1-texas-test 2025-01-01 2025-03-31 treatment=TX,CA holdout=NY,FL,OH
```

**Behavior:**
1. Parse and validate all parameters
2. Check geo coverage (geos exist in dim_geo, have data in date range)
3. Check date range validity (start < end, not in future, >= 14 days)
4. Insert into `experiments` with status = `queued`
5. Post confirmation to Slack with experiment details
6. Prefect worker picks up queued experiment and runs it
7. When complete, post results summary back to the originating channel

### `/geolift status <slug>`

Check the current status of an experiment.

**Example:**
```
/geolift status q1-texas-test
```

### `/geolift results <slug>`

Fetch and display results with plain-language interpretation.

**Example:**
```
/geolift results q1-texas-test
```

**Output includes:**
- Overall lift estimate with confidence interval
- Statistical significance assessment
- Plain-language interpretation
- Daily lift table (last 7 days or summary)

### `/geolift list`

List recent experiments with status.

### `/geolift help`

Show usage and examples.

---

## Natural Language Support

The experiment agent also responds to channel messages that mention GeoLift concepts:

- "run a geolift test for Texas" -> guided setup flow
- "what's the status of the texas experiment" -> status lookup
- "explain the lift results" -> interpretation of latest completed experiment
- "which geos have data" -> geo coverage check
- "best practices for holdout selection" -> guidance from knowledge base

---

## Data Validation Checks

Before queuing an experiment, validate:

1. **Geo existence**: All treatment and holdout geos exist in `dim_geo`
2. **Geo data coverage**: All geos have data in `fact_kpi_geo_daily` for the requested date range
3. **Date range**: start < end, range >= 14 days, end <= today
4. **No overlap**: Treatment and holdout geos don't overlap
5. **Minimum geos**: At least 1 treatment and 1 holdout geo
6. **Slug uniqueness**: No existing experiment with same slug (or warn about re-run)

---

## Results Interpretation

When posting results back to Slack, include:

- **Lift estimate**: "Revenue lift of +12.3% in treatment geos"
- **Confidence interval**: "90% CI: [+5.1%, +19.5%]"
- **Significance**: "Statistically significant at 90% confidence" or "Not significant"
- **Recommendation**: "The test shows a meaningful positive impact" or "Results are inconclusive"

---

## Files

| File | Purpose |
|------|---------|
| `services/slack-bot/src/experiment_agent.ts` | Slash command handler, validation, queuing, results posting |
| `services/slack-bot/src/index.ts` | Registers /geolift command and message handlers |
| `services/model-runner/src/geolift_runner.R` | Real GeoLift implementation |
| `services/model-runner/src/runner.py` | Orchestrator (already exists) |
| `services/model-runner/src/db.py` | DB helpers (already exists) |
| `orchestration/prefect/flows/run_experiments.py` | Prefect flow for queued experiments (already exists) |

---

## Environment Variables

Add to `services/slack-bot/.env`:

```
# Existing
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SUPABASE_URL=https://...
SUPABASE_SERVICE_KEY=...
SUPABASE_DB_URL=postgresql://...
OPENAI_API_KEY=sk-...

# New for experiment agent
SLACK_EXPERIMENT_CHANNEL_ID=C...  # Channel where results are posted
MODEL_RUNNER_DIR=../../services/model-runner/src  # Path to runner.py (for direct runs)
```

---

## Current Gaps (to implement)

1. **experiment_agent.ts** does not exist yet - needs full implementation
2. **geolift_runner.R** is a stub - needs real GeoLift::GeoLift() call
3. **/geolift slash command** not registered in index.ts
4. **Results callback** - no mechanism to post results back to Slack after Prefect finishes
5. **Natural language experiment routing** - index.ts only routes to analytics agent

---

## Implementation Priority

1. Create experiment_agent.ts with /geolift command parsing and validation
2. Wire /geolift into index.ts
3. Implement real GeoLift R logic
4. Add results polling/posting back to Slack
5. Add natural language experiment detection in message handler
