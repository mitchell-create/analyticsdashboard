"""Create TikTok period-level metrics function and cache table."""
import psycopg2

conn = psycopg2.connect(
    host='aws-1-us-east-2.pooler.supabase.com',
    port=5432,
    dbname='postgres',
    user='postgres.xopsomagbnsnadxxhzhx',
    password='Nf8V4JzKwRwZkLBU'
)
cur = conn.cursor()

# 1. Store TikTok access token in config table
cur.execute("""
INSERT INTO raw.meta_config (key, value, updated_at)
VALUES ('tiktok_access_token', '8475b03d2502d7a67de2ae7be2b522991a337bcd', NOW())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
""")
conn.commit()
print("[OK] TikTok access token stored")

# 2. Create TikTok cache table
cur.execute("""
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
)
""")
conn.commit()
print("[OK] TikTok cache table created")

# 3. Create TikTok API function
FUNC_SQL = r"""
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

    SELECT * INTO v_response FROM http(('GET', v_url, ARRAY[http_header('Access-Token', v_token)], NULL, NULL)::http_request);

    IF v_response.status = 200 THEN
        v_data := v_response.content::JSONB;

        IF (v_data->>'code')::int = 0 AND v_data->'data'->'list'->0 IS NOT NULL THEN
            v_metrics := v_data->'data'->'list'->0->'metrics';

            -- Upsert cache
            INSERT INTO raw.tiktok_period_metrics_cache
                (advertiser_id, date_start, date_end, frequency, reach, impressions, clicks, spend, cached_at)
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
"""
cur.execute(FUNC_SQL)
conn.commit()
print("[OK] TikTok period metrics function created")

# Test for Chubble Mar 1-11
cur.execute("SELECT * FROM raw.get_tiktok_period_metrics('6852902925644070917', '2026-03-01'::date, '2026-03-11'::date)")
row = cur.fetchone()
print(f"\nTest for Chubble TikTok Mar 1-11:")
print(f"  frequency={row[0]}, reach={row[1]}, impressions={row[2]}")
print(f"  clicks={row[3]}, spend={row[4]}")

conn.close()
print("\n[OK] All done!")
