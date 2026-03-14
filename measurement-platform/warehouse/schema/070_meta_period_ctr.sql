-- Period-Level Ad Platform Metrics: Postgres functions that call Meta's Marketing
-- API and TikTok's Reporting API for properly deduplicated unique metrics over
-- arbitrary date ranges.
--
-- WHY: Ad platform "unique" metrics (reach, frequency, unique clicks/CTR) are
-- deduplicated per-period. Daily Airbyte data overcounts because the same person
-- reached on multiple days is counted once per day. Summing daily reach gives
-- ~1.7-2x overcounting, making frequency appear ~50% lower and CTR ~30% lower
-- than what the ad platform dashboards show.
--
-- HOW: These functions call the platform APIs with the exact date range to get
-- period-level deduplicated values, then cache results for 24 hours.
--
-- USED BY:
--   Meta: Cards 421 (Unique Link Clicks), 422 (Unique CPC), 423 (Unique CTR),
--         335 (Frequency), 337 (CVR)
--   TikTok: Card 460 (Frequency)
--   Dashboards: Client Performance Template v2 (131), Chubble Gum Performance (162)

-- Enable HTTP extension for outbound API calls
CREATE EXTENSION IF NOT EXISTS http;

-- ============================================================================
-- META: Period-level metrics
-- ============================================================================

-- Cache table for period-level Meta insights
CREATE TABLE IF NOT EXISTS raw.meta_period_ctr_cache (
    account_id TEXT NOT NULL,
    date_start DATE NOT NULL,
    date_end DATE NOT NULL,
    unique_link_clicks_ctr NUMERIC,
    unique_ctr NUMERIC,
    reach BIGINT,
    unique_inline_link_clicks BIGINT,
    impressions BIGINT,
    frequency NUMERIC,
    clicks BIGINT,
    omni_purchase_count BIGINT,
    cached_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (account_id, date_start, date_end)
);

-- Config table for API access tokens (Meta + TikTok)
CREATE TABLE IF NOT EXISTS raw.meta_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Function: fetches period-level metrics from Meta Marketing API with 24h cache
CREATE OR REPLACE FUNCTION raw.get_meta_period_ctr(
    p_account_id TEXT,
    p_start DATE,
    p_end DATE,
    p_access_token TEXT DEFAULT NULL
) RETURNS TABLE (
    unique_link_clicks_ctr NUMERIC,
    unique_ctr NUMERIC,
    reach BIGINT,
    unique_inline_link_clicks BIGINT,
    impressions BIGINT,
    frequency NUMERIC,
    clicks BIGINT,
    omni_purchase_count BIGINT
) AS $$
DECLARE
    v_token TEXT;
    v_url TEXT;
    v_response http_response;
    v_data JSONB;
    v_row JSONB;
    v_cached RECORD;
    v_purchases BIGINT;
BEGIN
    -- Check cache first (24h TTL)
    SELECT c.unique_link_clicks_ctr, c.unique_ctr, c.reach,
           c.unique_inline_link_clicks, c.impressions,
           c.frequency, c.clicks, c.omni_purchase_count
    INTO v_cached
    FROM raw.meta_period_ctr_cache c
    WHERE c.account_id = p_account_id
      AND c.date_start = p_start
      AND c.date_end = p_end
      AND c.cached_at > NOW() - INTERVAL '24 hours';

    IF FOUND THEN
        RETURN QUERY SELECT v_cached.unique_link_clicks_ctr, v_cached.unique_ctr,
                            v_cached.reach, v_cached.unique_inline_link_clicks, v_cached.impressions,
                            v_cached.frequency, v_cached.clicks, v_cached.omni_purchase_count;
        RETURN;
    END IF;

    -- Get token (passed or from config table)
    v_token := COALESCE(p_access_token, (
        SELECT value FROM raw.meta_config WHERE key = 'access_token' LIMIT 1
    ));

    IF v_token IS NULL THEN
        RETURN QUERY SELECT NULL::NUMERIC, NULL::NUMERIC, NULL::BIGINT, NULL::BIGINT, NULL::BIGINT,
                            NULL::NUMERIC, NULL::BIGINT, NULL::BIGINT;
        RETURN;
    END IF;

    -- Call Meta Graph API for period-level insights
    v_url := 'https://graph.facebook.com/v21.0/act_' || p_account_id || '/insights?'
        || 'time_range={"since":"' || p_start::TEXT || '","until":"' || p_end::TEXT || '"}'
        || '&fields=unique_link_clicks_ctr,unique_ctr,reach,unique_inline_link_clicks,impressions,frequency,clicks,actions'
        || '&level=account'
        || '&access_token=' || v_token;

    SELECT * INTO v_response FROM http_get(v_url);

    IF v_response.status = 200 THEN
        v_data := v_response.content::JSONB;
        v_row := v_data->'data'->0;

        IF v_row IS NOT NULL THEN
            -- Extract omni_purchase count from actions array
            SELECT COALESCE((
                SELECT (elem->>'value')::BIGINT
                FROM jsonb_array_elements(v_row->'actions') elem
                WHERE elem->>'action_type' = 'omni_purchase'
                LIMIT 1
            ), 0) INTO v_purchases;

            -- Upsert cache
            INSERT INTO raw.meta_period_ctr_cache
                (account_id, date_start, date_end, unique_link_clicks_ctr, unique_ctr,
                 reach, unique_inline_link_clicks, impressions, frequency, clicks,
                 omni_purchase_count, cached_at)
            VALUES (
                p_account_id, p_start, p_end,
                (v_row->>'unique_link_clicks_ctr')::NUMERIC,
                (v_row->>'unique_ctr')::NUMERIC,
                (v_row->>'reach')::BIGINT,
                (v_row->>'unique_inline_link_clicks')::BIGINT,
                (v_row->>'impressions')::BIGINT,
                (v_row->>'frequency')::NUMERIC,
                (v_row->>'clicks')::BIGINT,
                v_purchases,
                NOW()
            )
            ON CONFLICT (account_id, date_start, date_end)
            DO UPDATE SET
                unique_link_clicks_ctr = EXCLUDED.unique_link_clicks_ctr,
                unique_ctr = EXCLUDED.unique_ctr,
                reach = EXCLUDED.reach,
                unique_inline_link_clicks = EXCLUDED.unique_inline_link_clicks,
                impressions = EXCLUDED.impressions,
                frequency = EXCLUDED.frequency,
                clicks = EXCLUDED.clicks,
                omni_purchase_count = EXCLUDED.omni_purchase_count,
                cached_at = NOW();

            RETURN QUERY SELECT
                (v_row->>'unique_link_clicks_ctr')::NUMERIC,
                (v_row->>'unique_ctr')::NUMERIC,
                (v_row->>'reach')::BIGINT,
                (v_row->>'unique_inline_link_clicks')::BIGINT,
                (v_row->>'impressions')::BIGINT,
                (v_row->>'frequency')::NUMERIC,
                (v_row->>'clicks')::BIGINT,
                v_purchases;
            RETURN;
        END IF;
    END IF;

    -- API failed: return NULLs (cards fall back to daily approximation)
    RETURN QUERY SELECT NULL::NUMERIC, NULL::NUMERIC, NULL::BIGINT, NULL::BIGINT, NULL::BIGINT,
                        NULL::NUMERIC, NULL::BIGINT, NULL::BIGINT;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- ============================================================================
-- TIKTOK: Period-level metrics
-- ============================================================================

-- Cache table for period-level TikTok insights
CREATE TABLE IF NOT EXISTS raw.tiktok_period_metrics_cache (
    advertiser_id TEXT NOT NULL,
    date_start DATE NOT NULL,
    date_end DATE NOT NULL,
    frequency NUMERIC,
    reach BIGINT,
    impressions BIGINT,
    clicks BIGINT,
    spend NUMERIC,
    cached_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (advertiser_id, date_start, date_end)
);

-- Function: fetches period-level metrics from TikTok Reporting API with 24h cache
CREATE OR REPLACE FUNCTION raw.get_tiktok_period_metrics(
    p_advertiser_id TEXT,
    p_start DATE,
    p_end DATE,
    p_access_token TEXT DEFAULT NULL
) RETURNS TABLE (
    frequency NUMERIC,
    reach BIGINT,
    impressions BIGINT,
    clicks BIGINT,
    spend NUMERIC
) AS $$
DECLARE
    v_token TEXT;
    v_url TEXT;
    v_response http_response;
    v_data JSONB;
    v_metrics JSONB;
    v_cached RECORD;
BEGIN
    -- Check cache first (24h TTL)
    SELECT c.frequency, c.reach, c.impressions, c.clicks, c.spend
    INTO v_cached
    FROM raw.tiktok_period_metrics_cache c
    WHERE c.advertiser_id = p_advertiser_id
      AND c.date_start = p_start
      AND c.date_end = p_end
      AND c.cached_at > NOW() - INTERVAL '24 hours';

    IF FOUND THEN
        RETURN QUERY SELECT v_cached.frequency, v_cached.reach,
                            v_cached.impressions, v_cached.clicks, v_cached.spend;
        RETURN;
    END IF;

    -- Get token (passed or from config table)
    v_token := COALESCE(p_access_token, (
        SELECT value FROM raw.meta_config WHERE key = 'tiktok_access_token' LIMIT 1
    ));

    IF v_token IS NULL THEN
        RETURN QUERY SELECT NULL::NUMERIC, NULL::BIGINT, NULL::BIGINT, NULL::BIGINT, NULL::NUMERIC;
        RETURN;
    END IF;

    -- Call TikTok Reporting API for period-level metrics
    v_url := 'https://business-api.tiktok.com/open_api/v1.3/report/integrated/get/'
        || '?advertiser_id=' || p_advertiser_id
        || '&report_type=BASIC'
        || '&data_level=AUCTION_ADVERTISER'
        || '&dimensions=["advertiser_id"]'
        || '&metrics=["frequency","reach","impressions","clicks","spend"]'
        || '&start_date=' || p_start::TEXT
        || '&end_date=' || p_end::TEXT
        || '&page=1&page_size=10';

    SELECT * INTO v_response FROM http(
        ('GET', v_url, ARRAY[http_header('Access-Token', v_token)], NULL, NULL)::http_request
    );

    IF v_response.status = 200 THEN
        v_data := v_response.content::JSONB;

        IF (v_data->>'code')::int = 0 AND v_data->'data'->'list'->0 IS NOT NULL THEN
            v_metrics := v_data->'data'->'list'->0->'metrics';

            -- Upsert cache
            INSERT INTO raw.tiktok_period_metrics_cache
                (advertiser_id, date_start, date_end, frequency, reach,
                 impressions, clicks, spend, cached_at)
            VALUES (
                p_advertiser_id, p_start, p_end,
                (v_metrics->>'frequency')::NUMERIC,
                (v_metrics->>'reach')::BIGINT,
                (v_metrics->>'impressions')::BIGINT,
                (v_metrics->>'clicks')::BIGINT,
                (v_metrics->>'spend')::NUMERIC,
                NOW()
            )
            ON CONFLICT (advertiser_id, date_start, date_end)
            DO UPDATE SET
                frequency = EXCLUDED.frequency,
                reach = EXCLUDED.reach,
                impressions = EXCLUDED.impressions,
                clicks = EXCLUDED.clicks,
                spend = EXCLUDED.spend,
                cached_at = NOW();

            RETURN QUERY SELECT
                (v_metrics->>'frequency')::NUMERIC,
                (v_metrics->>'reach')::BIGINT,
                (v_metrics->>'impressions')::BIGINT,
                (v_metrics->>'clicks')::BIGINT,
                (v_metrics->>'spend')::NUMERIC;
            RETURN;
        END IF;
    END IF;

    -- API failed: return NULLs
    RETURN QUERY SELECT NULL::NUMERIC, NULL::BIGINT, NULL::BIGINT, NULL::BIGINT, NULL::NUMERIC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
