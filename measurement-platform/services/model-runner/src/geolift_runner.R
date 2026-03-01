# geolift_runner.R — GeoLift runner (geo holdouts)
# Reads KPI by geo from Supabase (via CSV or API); runs GeoLift; writes results.
# Usage: Rscript geolift_runner.R <experiment_slug> <start_date> <end_date> <treatment_geos> <holdout_geos>
# treatment_geos / holdout_geos: comma-separated geo_id (e.g. TX,CA,NY).

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 5) {
  stop("Usage: Rscript geolift_runner.R <experiment_slug> <start_date> <end_date> <treatment_geos> <holdout_geos>")
}
experiment_slug <- args[1]
start_date     <- args[2]
end_date       <- args[3]
treatment_geos <- strsplit(args[4], ",")[[1]]
holdout_geos   <- strsplit(args[5], ",")[[1]]

# Optional: install GeoLift from GitHub
# remotes::install_github("facebookincubator/GeoLift")
if (!requireNamespace("GeoLift", quietly = TRUE)) {
  message("GeoLift not installed. Install with: remotes::install_github('facebookincubator/GeoLift')")
  message("Writing placeholder results for structure.")
  # Placeholder output for experiment_results
  result_date <- seq(as.Date(start_date), as.Date(end_date), by = "day")
  results <- data.frame(
    result_date = format(result_date, "%Y-%m-%d"),
    metric = "revenue",
    value = NA_real_,
    interval_lower = NA_real_,
    interval_upper = NA_real_,
    metadata = NA_character_
  )
  out_path <- sprintf("geolift_results_%s.csv", experiment_slug)
  write.csv(results, out_path, row.names = FALSE)
  message("Wrote ", out_path, " (placeholder). Configure GeoLift and re-run to produce real lift.")
  quit(save = "no", status = 0)
}

# Example GeoLift workflow (adapt to your data shape):
# 1. Load fact_kpi_geo_daily (wide: date x geo) — e.g. from CSV exported by runner.py
# 2. GeoLift::GeoLift() with treatment_geos, holdout_geos, pre-period, post-period
# 3. Extract daily lift and intervals; write to experiment_results format
# For now we write a stub that runner.py can call and then parse CSV output.

data_path <- Sys.getenv("GEOLIFT_DATA_CSV", sprintf("geolift_input_%s.csv", experiment_slug))
if (!file.exists(data_path)) {
  message("No ", data_path, " found. runner.py should export fact_kpi_geo_daily to this file.")
  result_date <- seq(as.Date(start_date), as.Date(end_date), by = "day")
  results <- data.frame(
    result_date = format(result_date, "%Y-%m-%d"),
    metric = "revenue",
    value = NA_real_,
    interval_lower = NA_real_,
    interval_upper = NA_real_,
    metadata = NA_character_
  )
  out_path <- sprintf("geolift_results_%s.csv", experiment_slug)
  write.csv(results, out_path, row.names = FALSE)
  message("Wrote ", out_path, " (placeholder).")
  quit(save = "no", status = 0)
}

# Placeholder: real GeoLift call would go here
# df <- read.csv(data_path)
# res <- GeoLift::GeoLift( ... )
# results <- data.frame(result_date=..., metric="revenue", value=res$lift, ...)
result_date <- seq(as.Date(start_date), as.Date(end_date), by = "day")
results <- data.frame(
  result_date = format(result_date, "%Y-%m-%d"),
  metric = "revenue",
  value = NA_real_,
  interval_lower = NA_real_,
  interval_upper = NA_real_,
  metadata = NA_character_
)
out_path <- sprintf("geolift_results_%s.csv", experiment_slug)
write.csv(results, out_path, row.names = FALSE)
message("Wrote ", out_path, ". Implement GeoLift::GeoLift() for real lift estimates.")
