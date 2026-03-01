-- Experiment Results: Experiments list (Table)
SELECT id, experiment_slug, experiment_type, start_date, end_date, status, config
FROM public.experiments
ORDER BY id DESC
