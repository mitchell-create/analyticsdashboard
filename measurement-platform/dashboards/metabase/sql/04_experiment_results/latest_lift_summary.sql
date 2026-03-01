-- Experiment Results: Latest lift summary (Table)
WITH latest AS (
  SELECT r.experiment_id, r.metric, r.value, r.interval_lower, r.interval_upper, r.result_date,
         ROW_NUMBER() OVER (PARTITION BY r.experiment_id, r.metric ORDER BY r.result_date DESC) AS rn
  FROM public.experiment_results r
)
SELECT e.experiment_slug, e.experiment_type, l.metric, l.value, l.interval_lower, l.interval_upper, l.result_date
FROM latest l
JOIN public.experiments e ON e.id = l.experiment_id
WHERE l.rn = 1
ORDER BY e.experiment_slug
