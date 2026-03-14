"""Expand get_meta_period_ctr() to return frequency, clicks, omni_purchase_count."""
import psycopg2

conn = psycopg2.connect(
    host='aws-1-us-east-2.pooler.supabase.com',
    port=5432,
    dbname='postgres',
    user='postgres.xopsomagbnsnadxxhzhx',
    password='Nf8V4JzKwRwZkLBU'
)
cur = conn.cursor()

# 1. Add new columns to cache table
cur.execute("""
ALTER TABLE raw.meta_period_ctr_cache
ADD COLUMN IF NOT EXISTS frequency NUMERIC,
ADD COLUMN IF NOT EXISTS clicks BIGINT,
ADD COLUMN IF NOT EXISTS omni_purchase_count BIGINT
""")
conn.commit()
print("[OK] Cache table columns added")

# 2. Drop and recreate function (signature changed - new return columns)
cur.execute("DROP FUNCTION IF EXISTS raw.get_meta_period_ctr(TEXT, DATE, DATE, TEXT)")
conn.commit()
print("[OK] Old function dropped")

# 3. Create expanded function
FUNC_SQL = r"""
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
"""
cur.execute(FUNC_SQL)
conn.commit()
print("[OK] Expanded function created")

# Clear cache so we get fresh data with new fields
cur.execute("DELETE FROM raw.meta_period_ctr_cache")
conn.commit()
print("[OK] Cache cleared")

# Test for Expand Mar 1-13
cur.execute("SELECT * FROM raw.get_meta_period_ctr('1382562625324999', '2026-03-01'::date, '2026-03-13'::date)")
row = cur.fetchone()
print(f"\nTest for Expand Mar 1-13:")
print(f"  unique_link_clicks_ctr={row[0]}, unique_ctr={row[1]}, reach={row[2]}")
print(f"  unique_inline_link_clicks={row[3]}, impressions={row[4]}")
print(f"  frequency={row[5]}, clicks={row[6]}, omni_purchase_count={row[7]}")
if row[6] and row[7]:
    cvr = round(float(row[7]) / float(row[6]) * 100, 2)
    print(f"  CVR (purchases/clicks*100) = {cvr}%")

# Test for Chubble Mar 1-11
cur.execute("SELECT * FROM raw.get_meta_period_ctr('752736179021770', '2026-03-01'::date, '2026-03-11'::date)")
row = cur.fetchone()
print(f"\nTest for Chubble Mar 1-11:")
print(f"  unique_link_clicks_ctr={row[0]}, unique_ctr={row[1]}, reach={row[2]}")
print(f"  unique_inline_link_clicks={row[3]}, impressions={row[4]}")
print(f"  frequency={row[5]}, clicks={row[6]}, omni_purchase_count={row[7]}")

conn.close()
print("\n[OK] All done!")
