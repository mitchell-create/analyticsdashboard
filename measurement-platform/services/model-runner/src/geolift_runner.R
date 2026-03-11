# geolift_runner.R — GeoLift geo-based incrementality test
# Reads KPI by geo from CSV (exported by runner.py); runs GeoLift; writes results CSV.
# Usage: Rscript geolift_runner.R <experiment_slug> <start_date> <end_date> <treatment_geos> <holdout_geos>
# treatment_geos / holdout_geos: comma-separated geo_id (e.g. TX,CA,NY).

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 5) {
  stop("Usage: Rscript geolift_runner.R <experiment_slug> <start_date> <end_date> <treatment_geos> <holdout_geos>")
}

experiment_slug <- args[1]
start_date      <- args[2]
end_date        <- args[3]
treatment_geos  <- strsplit(args[4], ",")[[1]]
holdout_geos    <- strsplit(args[5], ",")[[1]]
all_geos        <- c(treatment_geos, holdout_geos)

message("GeoLift runner: ", experiment_slug)
message("  Period: ", start_date, " to ", end_date)
message("  Treatment: ", paste(treatment_geos, collapse = ", "))
message("  Holdout: ", paste(holdout_geos, collapse = ", "))

out_path <- sprintf("geolift_results_%s.csv", experiment_slug)

# ── Check for GeoLift package ──────────────────────────────────────────────

if (!requireNamespace("GeoLift", quietly = TRUE)) {
  message("GeoLift package not installed.")
  message("Install with: remotes::install_github('facebookincubator/GeoLift')")
  message("Falling back to difference-in-means estimator.")
  USE_GEOLIFT <- FALSE
} else {
  USE_GEOLIFT <- TRUE
  library(GeoLift)
}

# ── Load data ──────────────────────────────────────────────────────────────

data_path <- Sys.getenv("GEOLIFT_DATA_CSV", sprintf("geolift_input_%s.csv", experiment_slug))
if (!file.exists(data_path)) {
  stop("Data file not found: ", data_path, ". runner.py should export fact_kpi_geo_daily to this file.")
}

raw <- read.csv(data_path, stringsAsFactors = FALSE)
message("  Loaded ", nrow(raw), " rows from ", data_path)

# Ensure date column is Date type
raw$report_date <- as.Date(raw$report_date)
raw$revenue <- as.numeric(raw$revenue)
raw$orders <- as.numeric(raw$orders)

# Filter to relevant geos and date range
df <- raw[raw$geo_id %in% all_geos &
           raw$report_date >= as.Date(start_date) &
           raw$report_date <= as.Date(end_date), ]

if (nrow(df) == 0) {
  stop("No data for specified geos and date range.")
}

message("  Filtered to ", nrow(df), " rows for ", length(unique(df$geo_id)), " geos")

# ── Run GeoLift or fallback ───────────────────────────────────────────────

if (USE_GEOLIFT) {
  # Pivot to wide format: rows = dates, cols = geos, values = revenue
  wide <- reshape(
    df[, c("report_date", "geo_id", "revenue")],
    idvar = "report_date",
    timevar = "geo_id",
    direction = "wide"
  )
  names(wide) <- gsub("^revenue\\.", "", names(wide))
  wide <- wide[order(wide$report_date), ]

  # Replace NAs with 0
  wide[is.na(wide)] <- 0

  date_seq <- wide$report_date
  n_dates <- length(date_seq)

  tryCatch({
    # Split pre/post at midpoint for GeoLift model
    mid_idx <- floor(n_dates / 2)

    gl_result <- GeoLift(
      Y_id = "revenue",
      data = df,
      locations = treatment_geos,
      treatment_start_time = mid_idx + 1,
      treatment_end_time = n_dates
    )

    # Extract results
    if (!is.null(gl_result$results)) {
      results <- data.frame(
        result_date = as.character(date_seq[(mid_idx + 1):n_dates]),
        metric = "revenue",
        value = gl_result$results$att,
        interval_lower = gl_result$results$att_lower,
        interval_upper = gl_result$results$att_upper,
        metadata = "estimator=geolift"
      )
    } else {
      # Fallback: use summary ATT
      results <- data.frame(
        result_date = as.character(date_seq[(mid_idx + 1):n_dates]),
        metric = "revenue",
        value = rep(gl_result$ATT, n_dates - mid_idx),
        interval_lower = rep(gl_result$ATT - 1.645 * gl_result$ATT_se, n_dates - mid_idx),
        interval_upper = rep(gl_result$ATT + 1.645 * gl_result$ATT_se, n_dates - mid_idx),
        metadata = "estimator=geolift-summary"
      )
    }

    write.csv(results, out_path, row.names = FALSE)
    message("GeoLift complete. Wrote ", out_path)

  }, error = function(e) {
    message("GeoLift model failed: ", e$message)
    message("Falling back to difference-in-means estimator.")
    USE_GEOLIFT <<- FALSE
  })
}

# ── Fallback: Difference-in-means estimator ───────────────────────────────

if (!USE_GEOLIFT || !file.exists(out_path)) {
  message("Using difference-in-means estimator.")

  # Split into treatment and holdout
  treatment_df <- df[df$geo_id %in% treatment_geos, ]
  holdout_df   <- df[df$geo_id %in% holdout_geos, ]

  # Aggregate daily revenue by group
  treatment_daily <- aggregate(revenue ~ report_date, data = treatment_df, FUN = sum)
  holdout_daily   <- aggregate(revenue ~ report_date, data = holdout_df, FUN = sum)

  # Normalize by number of geos (per-geo daily revenue)
  treatment_daily$revenue <- treatment_daily$revenue / length(treatment_geos)
  holdout_daily$revenue   <- holdout_daily$revenue / length(holdout_geos)

  # Merge on date
  merged <- merge(treatment_daily, holdout_daily, by = "report_date", suffixes = c("_treatment", "_holdout"))
  merged <- merged[order(merged$report_date), ]

  if (nrow(merged) == 0) {
    stop("No overlapping dates between treatment and holdout geos.")
  }

  # Split pre/post at midpoint
  mid_idx <- floor(nrow(merged) / 2)
  pre  <- merged[1:mid_idx, ]
  post <- merged[(mid_idx + 1):nrow(merged), ]

  # Pre-period difference (baseline)
  pre_diff <- mean(pre$revenue_treatment - pre$revenue_holdout, na.rm = TRUE)

  # Post-period lift = (post treatment - post holdout) - pre-period baseline diff
  post_diffs <- post$revenue_treatment - post$revenue_holdout
  lift_daily <- post_diffs - pre_diff

  # Scale back to total treatment geos
  lift_daily_total <- lift_daily * length(treatment_geos)

  # Confidence interval: t-distribution, 90% CI
  n_post <- length(lift_daily)
  se <- sd(lift_daily) / sqrt(n_post)
  t_crit <- qt(0.95, df = max(n_post - 1, 1))

  results <- data.frame(
    result_date = as.character(post$report_date),
    metric = "revenue",
    value = lift_daily_total,
    interval_lower = (lift_daily - t_crit * se) * length(treatment_geos),
    interval_upper = (lift_daily + t_crit * se) * length(treatment_geos),
    metadata = "estimator=difference-in-means"
  )

  write.csv(results, out_path, row.names = FALSE)
  message("Difference-in-means complete. Wrote ", out_path)
}

message("Done: ", experiment_slug)
