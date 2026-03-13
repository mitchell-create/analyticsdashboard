# geolift_runner.R — GeoLift geo-based incrementality test
# Reads KPI by geo from CSV (exported by runner.py); runs GeoLift; writes results CSV.
# Usage: Rscript geolift_runner.R <experiment_slug> <start_date> <end_date> <treatment_geos> <holdout_geos> [treatment_start_date]
# treatment_geos / holdout_geos: comma-separated geo_id (e.g. TX,CA,NY).
# treatment_start_date: optional YYYY-MM-DD when treatment actually began (if omitted, splits at data midpoint).

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 5) {
  stop("Usage: Rscript geolift_runner.R <slug> <start> <end> <treatment_geos> <holdout_geos> [treatment_start_date]")
}

experiment_slug     <- args[1]
start_date          <- args[2]
end_date            <- args[3]
treatment_geos      <- strsplit(args[4], ",")[[1]]
holdout_geos        <- strsplit(args[5], ",")[[1]]
treatment_start_date <- if (length(args) >= 6) args[6] else NULL
all_geos            <- c(treatment_geos, holdout_geos)

message("GeoLift runner: ", experiment_slug)
message("  Data period: ", start_date, " to ", end_date)
message("  Treatment: ", paste(treatment_geos, collapse = ", "))
message("  Holdout: ", paste(holdout_geos, collapse = ", "))
if (!is.null(treatment_start_date)) {
  message("  Treatment start: ", treatment_start_date)
}

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

# ── Helper: calculate pre/post split index ─────────────────────────────────

calc_split_index <- function(date_seq) {
  if (!is.null(treatment_start_date)) {
    tsd <- as.Date(treatment_start_date)
    pre_count <- sum(date_seq < tsd)
    if (pre_count > 0 && pre_count < length(date_seq)) {
      message("  Split at treatment_start_date: ", treatment_start_date,
              " (", pre_count, " pre-days, ", length(date_seq) - pre_count, " treatment-days)")
      return(pre_count)
    }
    message("  Warning: treatment_start_date outside data range, falling back to midpoint")
  }
  idx <- floor(length(date_seq) / 2)
  message("  Split at midpoint: index ", idx)
  return(idx)
}

# ── Run GeoLift or fallback ───────────────────────────────────────────────

if (USE_GEOLIFT) {
  # GeoLift requires data preprocessed by GeoDataRead().
  # GeoDataRead expects columns: date, location, Y (outcome).
  # It lowercases location names and creates a numeric time index.

  date_seq <- sort(unique(df$report_date))
  n_dates <- length(date_seq)
  mid_idx <- calc_split_index(date_seq)

  tryCatch({
    # Preprocess data with GeoDataRead (required by GeoLift)
    message("  Running GeoDataRead...")
    geo_data <- GeoDataRead(
      data = df,
      date_id = "report_date",
      location_id = "geo_id",
      Y_id = "revenue",
      X = c(),
      format = "yyyy-mm-dd",
      summary = TRUE
    )

    # GeoDataRead lowercases location names, so match treatment geos
    treatment_locs <- tolower(treatment_geos)
    message("  Treatment locations (lowercased): ", paste(treatment_locs, collapse = ", "))
    message("  treatment_start_time = ", mid_idx + 1, ", treatment_end_time = ", n_dates)

    # Run GeoLift Synthetic Control Model
    message("  Running GeoLift model...")
    gl_result <- GeoLift(
      Y_id = "Y",
      data = geo_data,
      locations = treatment_locs,
      treatment_start_time = mid_idx + 1,
      treatment_end_time = n_dates
    )

    message("  GeoLift completed successfully.")

    # ── Extract results from GeoLift object ──────────────────────────────────
    # GeoLift result structure:
    #   $ATT          — numeric vector length N (ALL dates, pre + treatment)
    #   $inference    — data.frame with ATT, Perc.Lift, pvalue, Lower/Upper CI
    #   $TreatmentStart, $TreatmentEnd — integer indices
    #   $incremental  — scalar total incremental Y
    #   $df_weights   — data.frame of control location weights
    #   $y_obs, $y_hat — observed vs synthetic control series

    # Extract p-value from inference table
    p_value_str <- "NA"
    perc_lift_str <- "NA"
    if (!is.null(gl_result$inference) && is.data.frame(gl_result$inference)) {
      if ("pvalue" %in% names(gl_result$inference)) {
        p_val <- gl_result$inference$pvalue[1]
        if (!is.na(p_val)) p_value_str <- as.character(round(p_val, 6))
      }
      if ("Perc.Lift" %in% names(gl_result$inference)) {
        pl <- gl_result$inference$Perc.Lift[1]
        if (!is.na(pl)) perc_lift_str <- as.character(round(pl, 2))
      }
    }
    message("  p-value: ", p_value_str, ", percent lift: ", perc_lift_str, "%")

    # Extract daily ATT for the treatment period only
    t_start <- gl_result$TreatmentStart
    t_end   <- gl_result$TreatmentEnd
    n_treatment <- t_end - t_start + 1

    if (!is.null(gl_result$ATT) && length(gl_result$ATT) >= t_end) {
      # ATT vector covers all dates; slice treatment period
      att_values <- gl_result$ATT[t_start:t_end]
    } else {
      # Fallback: use overall ATT from inference table
      att_overall <- if (!is.null(gl_result$inference$ATT)) gl_result$inference$ATT[1] else 0
      att_values <- rep(att_overall, n_treatment)
    }

    # Confidence intervals — try conformal inference bounds first
    ci_lower <- rep(NA, n_treatment)
    ci_upper <- rep(NA, n_treatment)
    if (!is.null(gl_result$inference)) {
      lb <- gl_result$inference$Lower.Conf.Int[1]
      ub <- gl_result$inference$Upper.Conf.Int[1]
      if (!is.na(lb) && !is.na(ub)) {
        ci_lower <- rep(lb, n_treatment)
        ci_upper <- rep(ub, n_treatment)
      }
    }
    # If CIs unavailable, estimate from pre-period ATT variance
    if (all(is.na(ci_lower)) && t_start > 10) {
      pre_att <- gl_result$ATT[1:(t_start - 1)]
      att_sd <- sd(pre_att, na.rm = TRUE)
      if (!is.na(att_sd) && att_sd > 0) {
        ci_lower <- att_values - 1.645 * att_sd
        ci_upper <- att_values + 1.645 * att_sd
        message("  CIs estimated from pre-period ATT variance (sd=", round(att_sd, 2), ")")
      }
    }

    # Build weights string for metadata
    weights_str <- ""
    if (!is.null(gl_result$df_weights) && is.data.frame(gl_result$df_weights)) {
      weights_str <- paste0(",weights=",
        paste(gl_result$df_weights$location, ":", round(gl_result$df_weights$weight, 3),
              collapse="|", sep=""))
    }

    # Incremental revenue
    incr_str <- ""
    if (!is.null(gl_result$incremental)) {
      incr_str <- paste0(",incremental=", round(gl_result$incremental, 2))
    }

    metadata_val <- paste0("estimator=geolift-scm,p_value=", p_value_str,
                           ",perc_lift=", perc_lift_str, "%",
                           incr_str, weights_str)

    results <- data.frame(
      result_date = as.character(date_seq[t_start:t_end]),
      metric = "revenue",
      value = att_values,
      interval_lower = ci_lower,
      interval_upper = ci_upper,
      metadata = metadata_val
    )

    write.csv(results, out_path, row.names = FALSE)
    message("GeoLift complete. p-value: ", p_value_str, ". Wrote ", nrow(results), " rows to ", out_path)

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

  # Split pre/post using treatment_start_date or midpoint
  mid_idx <- calc_split_index(merged$report_date)
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
