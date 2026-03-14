-- Meta Period-Level CTR: Postgres function that calls Meta's Marketing API
-- for properly deduplicated unique metrics over arbitrary date ranges.
--
-- WHY: Meta's "unique" metrics (unique_link_clicks_ctr, unique_ctr, reach)
-- are deduplicated per-period. Daily Airbyte data overcounts because the same
-- person reached on multiple days is counted once per day. Summing daily reach
-- gives ~1.7x overcounting, making CTR appear ~30% lower than Meta Ads Manager.
--
-- HOW: This function calls Meta's Graph API with the exact date range to get
-- period-level deduplicated values, then caches results for 24 hours.
--
-- USED BY: Metabase cards 421 (Unique Link Clicks), 422 (Unique CPC), 423 (Unique CTR)
-- on dashboards: Client Performance Template v2 (131), Chubble Gum Performance (162)

-- Enable HTTP extension for outbound API calls
CREATE EXTENSION IF NOT EXISTS http;

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
    cached_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (account_id, date_start, date_end)
);

-- Config table for Meta access token
CREATE TABLE IF NOT EXISTS raw.meta_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Function: fetches period-level CTR from Meta Marketing API with 24h cache
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
    impressions BIGINT
) AS $$
DECLARE
    v_token TEXT;
    v_url TEXT;
    v_response http_response;
    v_data JSONB;
    v_row JSONB;
    v_cached RECORD;
BEGIN
    -- Check cache first (24h TTL)
    SELECT c.unique_link_clicks_ctr, c.unique_ctr, c.reach,
           c.unique_inline_link_clicks, c.impressions
    INTO v_cached
    FROM raw.meta_period_ctr_cache c
    WHERE c.account_id = p_account_id
      AND c.date_start = p_start
      AND c.date_end = p_end
      AND c.cached_at > NOW() - INTERVAL '24 hours';

    IF FOUND THEN
        RETURN QUERY SELECT v_cached.unique_link_clicks_ctr, v_cached.unique_ctr,
                            v_cached.reach, v_cached.unique_inline_link_clicks, v_cached.impressions;
        RETURN;
    END IF;

    -- Get token (passed or from config table)
    v_token := COALESCE(p_access_token, (
        SELECT value FROM raw.meta_config WHERE key = 'access_token' LIMIT 1
    ));

    IF v_token IS NULL THEN
        RETURN QUERY SELECT NULL::NUMERIC, NULL::NUMERIC, NULL::BIGINT, NULL::BIGINT, NULL::BIGINT;
        RETURN;
    END IF;

    -- Call Meta Graph API for period-level insights
    v_url := 'https://graph.facebook.com/v21.0/act_' || p_account_id || '/insights?'
        || 'time_range={"since":"' || p_start::TEXT || '","until":"' || p_end::TEXT || '"}'
        || '&fields=unique_link_clicks_ctr,unique_ctr,reach,unique_inline_link_clicks,impressions'
        || '&level=account'
        || '&access_token=' || v_token;

    SELECT * INTO v_response FROM http_get(v_url);

    IF v_response.status = 200 THEN
        v_data := v_response.content::JSONB;
        v_row := v_data->'data'->0;

        IF v_row IS NOT NULL THEN
            -- Upsert cache
            INSERT INTO raw.meta_period_ctr_cache
                (account_id, date_start, date_end, unique_link_clicks_ctr, unique_ctr,
                 reach, unique_inline_link_clicks, impressions, cached_at)
            VALUES (
                p_account_id, p_start, p_end,
                (v_row->>'unique_link_clicks_ctr')::NUMERIC,
                (v_row->>'unique_ctr')::NUMERIC,
                (v_row->>'reach')::BIGINT,
                (v_row->>'unique_inline_link_clicks')::BIGINT,
                (v_row->>'impressions')::BIGINT,
                NOW()
            )
            ON CONFLICT (account_id, date_start, date_end)
            DO UPDATE SET
                unique_link_clicks_ctr = EXCLUDED.unique_link_clicks_ctr,
                unique_ctr = EXCLUDED.unique_ctr,
                reach = EXCLUDED.reach,
                unique_inline_link_clicks = EXCLUDED.unique_inline_link_clicks,
                impressions = EXCLUDED.impressions,
                cached_at = NOW();

            RETURN QUERY SELECT
                (v_row->>'unique_link_clicks_ctr')::NUMERIC,
                (v_row->>'unique_ctr')::NUMERIC,
                (v_row->>'reach')::BIGINT,
                (v_row->>'unique_inline_link_clicks')::BIGINT,
                (v_row->>'impressions')::BIGINT;
            RETURN;
        END IF;
    END IF;

    -- API failed: return NULL (cards fall back to daily approximation)
    RETURN QUERY SELECT NULL::NUMERIC, NULL::NUMERIC, NULL::BIGINT, NULL::BIGINT, NULL::BIGINT;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
