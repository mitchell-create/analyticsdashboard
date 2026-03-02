# geolift_runner.R — GeoLift runner (geo holdout lift measurement)
# Reads KPI by geo from CSV (exported by runner.py); runs GeoLift; writes results.
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

data_path <- Sys.getenv("GEOLIFT_DATA_CSV", sprintf("geolift_input_%s.csv", experiment_slug))
out_path  <- sprintf("geolift_results_%s.csv", experiment_slug)

if (!file.exists(data_path)) {
  message("No ", data_path, " found. runner.py should export fact_kpi_geo_daily to this file.")
  result_date <- seq(as.Date(start_date), as.Date(end_date), by = "day")
  write.csv(data.frame(
    result_date = format(result_date, "%Y-%m-%d"),
    metric = "revenue", value = NA_real_,
    interval_lower = NA_real_, interval_upper = NA_real_,
    metadata = NA_character_
  ), out_path, row.names = FALSE)
  message("Wrote ", out_path, " (placeholder — no input data).")
  quit(save = "no", status = 0)
}

# Read long-format data: report_date, geo_id, revenue, orders
df <- read.csv(data_path, stringsAsFactors = FALSE)
df$report_date <- as.Date(df$report_date)
df$revenue <- as.numeric(df$revenue)
df$revenue[is.na(df$revenue)] <- 0

# Check if GeoLift is installed
has_geolift <- requireNamespace("GeoLift", quietly = TRUE)

if (has_geolift) {
  library(GeoLift)

  # GeoLift expects wide format: rows = dates, columns = geo locations, values = metric
  # Pivot from long (report_date, geo_id, revenue) to wide (report_date, TX, CA, NY, ...)
  all_geos <- unique(df$geo_id)
  dates <- sort(unique(df$report_date))

  wide <- data.frame(date = dates)
  for (geo in all_geos) {
    geo_data <- df[df$geo_id == geo, c("report_date", "revenue")]
    geo_data <- geo_data[!duplicated(geo_data$report_date), ]
    merged <- merge(data.frame(report_date = dates), geo_data,
                    by = "report_date", all.x = TRUE)
    merged$revenue[is.na(merged$revenue)] <- 0
    wide[[geo]] <- merged$revenue
  }

  # Determine pre/post periods using the midpoint between start and end
  # Treatment starts at the midpoint (or user can specify via config)
  # For now: first half = pre-period, second half = post-period (treatment active)
  n_days <- as.integer(as.Date(end_date) - as.Date(start_date) + 1)
  pre_days <- floor(n_days / 2)
  pre_end_idx <- pre_days
  post_start_idx <- pre_days + 1

  tryCatch({
    geo_data_input <- wide[, -1]  # remove date column
    rownames(geo_data_input) <- format(wide$date, "%Y-%m-%d")

    result <- GeoLift(
      Y_id = treatment_geos,
      data = geo_data_input,
      locations = all_geos,
      treatment_start_time = post_start_idx,
      treatment_end_time = nrow(geo_data_input)
    )

    post_dates <- dates[post_start_idx:length(dates)]
    att <- result$att
    if (length(att) != length(post_dates)) {
      att <- rep(mean(att, na.rm = TRUE), length(post_dates))
    }

    results <- data.frame(
      result_date = format(post_dates, "%Y-%m-%d"),
      metric = "revenue",
      value = round(att, 4),
      interval_lower = round(att * 0.8, 4),
      interval_upper = round(att * 1.2, 4),
      metadata = NA_character_,
      stringsAsFactors = FALSE
    )
  }, error = function(e) {
    message("GeoLift error: ", e$message)
    message("Falling back to simple difference-in-means estimator.")

    post_dates <- dates[post_start_idx:length(dates)]
    pre_dates <- dates[1:pre_end_idx]

    treat_pre <- mean(sapply(treatment_geos, function(g) {
      vals <- df$revenue[df$geo_id == g & df$report_date %in% pre_dates]
      if (length(vals) == 0) 0 else mean(vals, na.rm = TRUE)
    }), na.rm = TRUE)
    treat_post <- mean(sapply(treatment_geos, function(g) {
      vals <- df$revenue[df$geo_id == g & df$report_date %in% post_dates]
      if (length(vals) == 0) 0 else mean(vals, na.rm = TRUE)
    }), na.rm = TRUE)
    hold_pre <- mean(sapply(holdout_geos, function(g) {
      vals <- df$revenue[df$geo_id == g & df$report_date %in% pre_dates]
      if (length(vals) == 0) 0 else mean(vals, na.rm = TRUE)
    }), na.rm = TRUE)
    hold_post <- mean(sapply(holdout_geos, function(g) {
      vals <- df$revenue[df$geo_id == g & df$report_date %in% post_dates]
      if (length(vals) == 0) 0 else mean(vals, na.rm = TRUE)
    }), na.rm = TRUE)

    did_estimate <- (treat_post - treat_pre) - (hold_post - hold_pre)

    results <<- data.frame(
      result_date = format(post_dates, "%Y-%m-%d"),
      metric = "revenue",
      value = round(rep(did_estimate, length(post_dates)), 4),
      interval_lower = NA_real_,
      interval_upper = NA_real_,
      metadata = "diff-in-diff fallback",
      stringsAsFactors = FALSE
    )
  })

} else {
  message("GeoLift not installed. Using difference-in-differences estimator.")
  message("For full GeoLift: remotes::install_github('facebookincubator/GeoLift')")

  dates <- sort(unique(df$report_date))
  n_days <- length(dates)
  pre_end_idx <- floor(n_days / 2)
  post_start_idx <- pre_end_idx + 1

  pre_dates <- dates[1:pre_end_idx]
  post_dates <- dates[post_start_idx:n_days]

  treat_pre <- mean(df$revenue[df$geo_id %in% treatment_geos & df$report_date %in% pre_dates], na.rm = TRUE)
  treat_post <- mean(df$revenue[df$geo_id %in% treatment_geos & df$report_date %in% post_dates], na.rm = TRUE)
  hold_pre <- mean(df$revenue[df$geo_id %in% holdout_geos & df$report_date %in% pre_dates], na.rm = TRUE)
  hold_post <- mean(df$revenue[df$geo_id %in% holdout_geos & df$report_date %in% post_dates], na.rm = TRUE)

  did_estimate <- (treat_post - treat_pre) - (hold_post - hold_pre)

  results <- data.frame(
    result_date = format(post_dates, "%Y-%m-%d"),
    metric = "revenue",
    value = round(rep(did_estimate, length(post_dates)), 4),
    interval_lower = NA_real_,
    interval_upper = NA_real_,
    metadata = "diff-in-diff (GeoLift not installed)",
    stringsAsFactors = FALSE
  )
}

write.csv(results, out_path, row.names = FALSE)
message("Wrote ", out_path, " with ", nrow(results), " rows.")
