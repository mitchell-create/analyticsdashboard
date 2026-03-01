-- 040_experiments.sql — Experiments and experiment results (GeoLift, CausalImpact)

CREATE TABLE IF NOT EXISTS public.experiments (
  id            BIGSERIAL PRIMARY KEY,
  experiment_slug TEXT NOT NULL UNIQUE,
  experiment_type TEXT NOT NULL,  -- 'geolift', 'causal_impact'
  start_date   DATE NOT NULL,
  end_date     DATE NOT NULL,
  config       JSONB,           -- holdout geos, treatment geos, etc.
  status       TEXT NOT NULL DEFAULT 'draft',  -- draft, queued, running, completed, failed
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_experiments_slug ON public.experiments (experiment_slug);
CREATE INDEX IF NOT EXISTS idx_experiments_status ON public.experiments (status);

COMMENT ON TABLE public.experiments IS 'Experiment definitions (GeoLift, CausalImpact).';

CREATE TABLE IF NOT EXISTS public.experiment_results (
  id            BIGSERIAL PRIMARY KEY,
  experiment_id BIGINT NOT NULL REFERENCES public.experiments (id),
  result_date   DATE NOT NULL,   -- daily result date
  metric        TEXT NOT NULL,   -- e.g. 'revenue', 'orders'
  value         NUMERIC(18, 4),
  interval_lower NUMERIC(18, 4),
  interval_upper NUMERIC(18, 4),
  metadata      JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (experiment_id, result_date, metric)
);

CREATE INDEX IF NOT EXISTS idx_experiment_results_experiment ON public.experiment_results (experiment_id);
CREATE INDEX IF NOT EXISTS idx_experiment_results_date ON public.experiment_results (result_date);

COMMENT ON TABLE public.experiment_results IS 'GeoLift/CausalImpact outputs for dashboards.';
