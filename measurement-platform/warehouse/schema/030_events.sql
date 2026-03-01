-- 030_events.sql — Marketing events (email blasts, promos)

CREATE TABLE IF NOT EXISTS public.marketing_events (
  id            BIGSERIAL PRIMARY KEY,
  event_date    DATE NOT NULL,
  event_type    TEXT NOT NULL,   -- e.g. 'email_blast', 'promo_start', 'promo_end'
  event_name    TEXT,
  source        TEXT,            -- e.g. 'klaviyo', 'manual'
  metadata      JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_marketing_events_date ON public.marketing_events (event_date);
CREATE INDEX IF NOT EXISTS idx_marketing_events_type ON public.marketing_events (event_type);

COMMENT ON TABLE public.marketing_events IS 'Major marketing events for reporting context (email blasts, promos).';
