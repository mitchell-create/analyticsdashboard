# GeoLift + Slack Agent — Spec for Next Agent

This document explains everything related to the GeoLift test, the AI agent, and Slack integration so another agent can extend or incorporate these capabilities.

---

## 1. GeoLift Test — Overview & Capabilities

### What GeoLift Is

GeoLift is a geo-based incrementality test that measures the true lift of ad campaigns using Synthetic Control Methods. You run ads in some geos (treatment) and not in others (holdout), then compare outcomes to estimate incremental revenue/orders.

- **Source:** [facebookincubator/GeoLift](https://github.com/facebookincubator/GeoLift)
- **Method:** Synthetic control / matrix completion
- **Input:** Daily KPI (revenue, orders) by geography
- **Output:** Daily lift estimates with confidence intervals

### Current Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| **Python orchestrator** | ✅ Implemented | `services/model-runner/src/runner.py` |
| **R script (geolift_runner.R)** | ⚠️ **Stub only** | Does NOT call `GeoLift::GeoLift()` — writes placeholder NA results |
| **Data pipeline** | ✅ Ready | `fact_kpi_geo_daily` populated from Shopify orders by province |
| **Prefect flow** | ✅ Implemented | Runs queued experiments via `run_experiments` flow |
| **DB tables** | ✅ Ready | `experiments`, `experiment_results` in Supabase |

### How to Run GeoLift (Once Implemented)

```bash
# Via Python runner (manual)
cd measurement-platform/services/model-runner/src
python runner.py geolift <slug> <start_date> <end_date> <treatment_geos> <holdout_geos>
# Example: python runner.py geolift my-test 2024-01-01 2024-02-28 "TX,CA" "NY,FL"

# Via Prefect (queued)
# 1. Insert row into experiments with status='queued', config={treatment_geos, holdout_geos}
# 2. run_experiments flow picks it up and runs model-runner
```

### Data Flow

1. **Input:** `public_marts.fact_kpi_geo_daily` (report_date, geo_id, revenue, orders)
   - Built by dbt from Shopify orders (`stg_shopify_orders_geo` → province_code)
   - Joined to `dim_geo` (geo_id = state/province code, e.g. TX, CA)

2. **Process:** runner.py fetches data → exports CSV → calls R script → R (when implemented) runs GeoLift

3. **Output:** Results written to `public.experiment_results`:
   - result_date, metric (revenue/orders), value (lift), interval_lower, interval_upper

### GeoLift Best Practices (Embedded in Agent)

- **Data:** Daily granularity; 4–5× pre-period vs test; 25+ pre-treatment periods; 20+ geos; 52+ weeks history; no missing values
- **Test duration:** Min 15 days (daily) or 4–6 weeks (weekly)
- **Markets:** Match test/control on outcome; keep local marketing constant; hold national media constant

---

## 2. AI Agent — Current Capabilities

### Experiment Agent (`experiment_agent.ts`)

**Purpose:** Guides users on GeoLift setup, best practices, and CausalImpact.

**Capabilities:**
- Answers questions about GeoLift setup, treatment vs holdout selection, pre-period requirements
- Explains CausalImpact (time-series pre/post) and how to run it
- Fetches **context from DB:** current experiments (slug, type, dates, status), geo data summary (how many geos, date range)
- Uses OpenAI gpt-4o (configurable via OPENAI_AGENT_MODEL)
- Triggered by keywords: geolift, geo lift, experiment setup, incrementality, treatment geos, holdout geos, etc.

**What it does NOT do:**
- Run experiments
- Insert experiments into the DB
- Post results to Slack when a test completes

### Analytics / Data Agent (`ai_to_sql.ts`)

**Purpose:** Converts natural language to SQL and returns data.

**Capabilities:**
- Pattern-matched queries (spend by channel, revenue in Texas, TikTok views)
- LLM-generated SQL for flexible questions (with OPENAI_API_KEY)
- Report mode: "ecom summary", "make a report", comparison ("vs previous 7 days")
- **Allowlisted tables:** fact_spend_daily, fact_kpi_daily, fact_kpi_geo_daily, dim_geo, experiments, experiment_results, etc.
- Guardrails: SELECT only; no INSERT/UPDATE/DELETE

**What it can answer:**
- "Spend by channel", "Revenue last month", "Show GeoLift results", "Experiments status"

---

## 3. Slack Integration — Current State

### Slash Commands

| Command | Purpose | Handler |
|---------|---------|---------|
| `/analytics <question>` | Data Q&A, reports | `answerQuery` (ai_to_sql) |
| `/geolift [question]` | GeoLift/experiment guidance | `answerExperimentQuery` (experiment_agent) |

### Channel Messages

- Bot responds to **all messages** in channels it's invited to (no @mention required)
- Routing: if message contains experiment triggers → experiment agent; else → analytics (report mode or SQL)

### Env Vars (Slack Bot)

- SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET
- SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_DB_URL
- OPENAI_API_KEY (required for both agents)
- OPENAI_MODEL (optional, default gpt-4o-mini for SQL/reports)
- OPENAI_AGENT_MODEL (optional, default gpt-4o for experiment agent)

### Alerts (Separate)

- Prefect posts pipeline failure alerts to SLACK_ALERT_CHANNEL_ID (not experiment-specific)

---

## 4. What the Next Agent Needs to Do

### Gaps & Desired Enhancements

1. **Run GeoLift from Slack**
   - User: "Run a GeoLift test: slug=spring-campaign, start=2024-03-01, end=2024-03-31, treatment=TX,CA, holdout=NY,FL"
   - Agent: Insert into `experiments` (status=queued or running), trigger `run_experiments` or call model-runner, confirm in Slack

2. **Create/queue experiments via Slack**
   - User: "Queue a GeoLift experiment for next month with TX and CA as treatment"
   - Agent: Parse params, insert row into `experiments`, reply with confirmation

3. **Post results when test completes**
   - When Prefect/model-runner finishes an experiment, post a summary to Slack (e.g. #measurement-alerts or a designated channel)
   - Include: experiment_slug, lift estimate, confidence interval, link to Metabase

4. **Interpret results in Slack**
   - User: "Explain the results of spring-campaign" or "What does the lift mean for experiment X?"
   - Agent: Fetch from experiment_results, summarize in plain language, explain significance

5. **Data validation before running**
   - User asks to run GeoLift
   - Agent: Check fact_kpi_geo_daily for sufficient geos, date range, no gaps
   - Warn if data doesn't meet best practices (e.g. < 20 geos, < 25 pre-period days)

6. **Complete the R implementation**
   - geolift_runner.R is a stub; needs real `GeoLift::GeoLift()` call
   - Transform CSV to GeoLift format (wide: date × geo), call package, extract lift/CI

### Technical Requirements for Next Agent

- **Read:** experiments, experiment_results, fact_kpi_geo_daily (via runReadOnlyQuery or Supabase)
- **Write:** experiments (insert/update) — requires WRITE access; currently bot is read-only
- **Trigger:** Prefect `run_experiments` flow or subprocess to runner.py
- **Slack:** Post to channel (chat.postMessage) — bot already has chat:write
- **New slash command?** e.g. `/run-geolift` or extend `/geolift` to accept params

### Files to Modify

| File | Purpose |
|------|---------|
| `services/slack-bot/src/experiment_agent.ts` | Add run/queue logic, result interpretation |
| `services/slack-bot/src/index.ts` | New `/run-geolift` or enhanced `/geolift` |
| `services/slack-bot/src/db.ts` | Add `insertExperiment()` if agent writes to DB |
| `services/model-runner/src/geolift_runner.R` | Implement real GeoLift call |
| `orchestration/prefect/flows/run_experiments.py` | Optional: post to Slack on completion |

---

## 5. Database Schema Reference

### experiments

| Column | Type | Notes |
|--------|------|-------|
| id | BIGSERIAL | PK |
| experiment_slug | TEXT | Unique, e.g. "spring-2024" |
| experiment_type | TEXT | 'geolift' or 'causal_impact' |
| start_date | DATE | |
| end_date | DATE | |
| config | JSONB | {treatment_geos: [...], holdout_geos: [...]} for geolift |
| status | TEXT | draft, queued, running, completed, failed |

### experiment_results

| Column | Type | Notes |
|--------|------|-------|
| experiment_id | BIGINT | FK to experiments |
| result_date | DATE | Daily result |
| metric | TEXT | 'revenue', 'orders' |
| value | NUMERIC | Lift estimate |
| interval_lower | NUMERIC | CI lower |
| interval_upper | NUMERIC | CI upper |

---

## 6. Summary for Next Agent

**Current state:**
- GeoLift orchestration exists but R script is a stub (no real lift calculation).
- Slack has an experiment agent (guidance + DB context) and analytics agent (SQL/reports).
- Experiments can be queued via Prefect by inserting into `experiments` with status=queued.

**Next agent should:**
1. Allow users to **create/run GeoLift experiments from Slack** (parse params, insert experiment, trigger runner).
2. **Post experiment results to Slack** when tests complete.
3. **Interpret and explain results** on demand.
4. Optionally **complete geolift_runner.R** so real lift is computed.
5. **Validate data** before running (geo count, date range, best practices).
