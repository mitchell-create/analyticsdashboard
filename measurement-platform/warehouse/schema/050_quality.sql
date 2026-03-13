-- 050_quality.sql — QA and monitoring (data_quality_flags, pipeline_runs, ai_query_audit)

CREATE TABLE IF NOT EXISTS public.data_quality_flags (
  id            BIGSERIAL PRIMARY KEY,
  flag_date     DATE NOT NULL,
  check_name    TEXT NOT NULL,
  severity      TEXT NOT NULL,  -- 'warning', 'error', 'critical'
  message       TEXT,
  metadata      JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_quality_flags_date ON public.data_quality_flags (flag_date);
CREATE INDEX IF NOT EXISTS idx_data_quality_flags_check ON public.data_quality_flags (check_name);

COMMENT ON TABLE public.data_quality_flags IS 'Data quality check results (missing dates, anomalies).';

CREATE TABLE IF NOT EXISTS public.pipeline_runs (
  id            BIGSERIAL PRIMARY KEY,
  run_date      DATE NOT NULL,
  flow_name     TEXT NOT NULL,   -- e.g. 'daily_pipeline', 'run_experiments'
  status        TEXT NOT NULL,   -- 'success', 'failed', 'running'
  started_at   TIMESTAMPTZ NOT NULL,
  finished_at   TIMESTAMPTZ,
  message       TEXT,
  metadata      JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_date ON public.pipeline_runs (run_date);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_flow ON public.pipeline_runs (flow_name);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON public.pipeline_runs (status);

COMMENT ON TABLE public.pipeline_runs IS 'Orchestration run history (Prefect).';

CREATE TABLE IF NOT EXISTS public.ai_query_audit (
  id            BIGSERIAL PRIMARY KEY,
  query_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  user_id       TEXT,
  channel_id    TEXT,
  client_slug   TEXT,             -- which client DB was queried (multi-client routing)
  prompt        TEXT,
  sql_executed  TEXT,
  table_used    TEXT,
  row_count    INT,
  error_message TEXT,
  metadata      JSONB
);

CREATE INDEX IF NOT EXISTS idx_ai_query_audit_query_at ON public.ai_query_audit (query_at);

COMMENT ON TABLE public.ai_query_audit IS 'Slack bot Q&A query log and receipts.';
