-- Experiment Results: Lift over time (Line chart)
SELECT e.experiment_slug, r.result_date AS date, r.metric, r.value, r.interval_lower, r.interval_upper
FROM public.experiment_results r
JOIN public.experiments e ON e.id = r.experiment_id
ORDER BY e.experiment_slug, r.result_date
