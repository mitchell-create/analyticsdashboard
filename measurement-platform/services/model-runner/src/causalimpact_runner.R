# causalimpact_runner.R — CausalImpact runner (time-series lift, e.g. organic TikTok impact)
# Reads daily KPI / TikTok organic from Supabase (via CSV); runs CausalImpact; writes results.
# Usage: Rscript causalimpact_runner.R <experiment_slug> <start_date> <end_date> <intervention_date> [metric]
# metric: revenue | orders | views (default revenue).

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 4) {
  stop("Usage: Rscript causalimpact_runner.R <experiment_slug> <start_date> <end_date> <intervention_date> [metric]")
}
experiment_slug   <- args[1]
start_date       <- args[2]
end_date         <- args[3]
intervention_date <- args[4]
metric           <- if (length(args) >= 5) args[5] else "revenue"

# Optional: install CausalImpact
# install.packages("CausalImpact")
if (!requireNamespace("CausalImpact", quietly = TRUE)) {
  message("CausalImpact not installed. Install with: install.packages('CausalImpact')")
  message("Writing placeholder results for structure.")
  result_date <- seq(as.Date(start_date), as.Date(end_date), by = "day")
  results <- data.frame(
    result_date = format(result_date, "%Y-%m-%d"),
    metric = metric,
    value = NA_real_,
    interval_lower = NA_real_,
    interval_upper = NA_real_,
    metadata = NA_character_
  )
  out_path <- sprintf("causalimpact_results_%s.csv", experiment_slug)
  write.csv(results, out_path, row.names = FALSE)
  message("Wrote ", out_path, " (placeholder).")
  quit(save = "no", status = 0)
}

data_path <- Sys.getenv("CAUSALIMPACT_DATA_CSV", sprintf("causalimpact_input_%s.csv", experiment_slug))
if (!file.exists(data_path)) {
  message("No ", data_path, " found. runner.py should export daily series to this file.")
  result_date <- seq(as.Date(start_date), as.Date(end_date), by = "day")
  results <- data.frame(
    result_date = format(result_date, "%Y-%m-%d"),
    metric = metric,
    value = NA_real_,
    interval_lower = NA_real_,
    interval_upper = NA_real_,
    metadata = NA_character_
  )
  out_path <- sprintf("causalimpact_results_%s.csv", experiment_slug)
  write.csv(results, out_path, row.names = FALSE)
  message("Wrote ", out_path, " (placeholder).")
  quit(save = "no", status = 0)
}

# Run CausalImpact
df <- read.csv(data_path, stringsAsFactors = FALSE)
df$report_date <- as.Date(df$report_date)

# Metric column: revenue, orders, or views
metric_col <- if (metric == "orders") "orders" else if (metric == "views") "views" else "revenue"
if (!metric_col %in% names(df)) {
  metric_col <- names(df)[2]  # fallback: second column
}
y <- as.numeric(df[[metric_col]])
y[is.na(y)] <- 0

# Build zoo time series (CausalImpact expects zoo or ts)
if (!requireNamespace("zoo", quietly = TRUE)) {
  install.packages("zoo", repos = "https://cloud.r-project.org")
}
library(zoo)
z <- zoo::zoo(y, df$report_date)

# Pre/post period: pre = before intervention, post = from intervention onward
pre_end <- as.Date(intervention_date) - 1
post_start <- as.Date(intervention_date)
pre_idx <- which(df$report_date <= pre_end)
post_idx <- which(df$report_date >= post_start)
if (length(pre_idx) < 10) {
  message("Warning: need at least 10 pre-intervention points. Got ", length(pre_idx))
}
if (length(post_idx) == 0) {
  message("Warning: no post-intervention data.")
}

# CausalImpact expects c(start, end) - use dates for zoo
pre_period <- c(as.Date(start_date), pre_end)
post_period <- c(post_start, as.Date(end_date))

impact <- CausalImpact::CausalImpact(z, pre_period, post_period, model.args = list(niter = 2000))

# Extract daily lift (effect = actual - counterfactual) for post period
post_dates <- df$report_date[post_idx]
point_effect <- as.numeric(impact$series$response[post_idx]) - as.numeric(impact$series$point.pred[post_idx])
effect_lower <- as.numeric(impact$series$response[post_idx]) - as.numeric(impact$series$point.pred.upper[post_idx])
effect_upper <- as.numeric(impact$series$response[post_idx]) - as.numeric(impact$series$point.pred.lower[post_idx])

results <- data.frame(
  result_date = format(post_dates, "%Y-%m-%d"),
  metric = metric,
  value = round(point_effect, 4),
  interval_lower = round(effect_lower, 4),
  interval_upper = round(effect_upper, 4),
  metadata = NA_character_,
  stringsAsFactors = FALSE
)
out_path <- sprintf("causalimpact_results_%s.csv", experiment_slug)
write.csv(results, out_path, row.names = FALSE)
message("Wrote ", out_path, " with ", nrow(results), " daily lift estimates.")
