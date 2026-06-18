-- Protect against provider-specific prefixes (for example Meta "act_123")
-- causing spend rows to be dropped from fact_spend_daily joins.
with accounts as (
    select
        'client_a' as client_slug,
        'meta' as platform,
        '123456789' as account_id,
        regexp_replace('123456789', '[^0-9]', '', 'g') as normalized_account_id
),

staged_spend as (
    select
        'act_123456789' as account_id,
        date '2026-05-01' as report_date,
        'meta' as channel,
        42::numeric as spend
),

joined as (
    select staged_spend.spend
    from staged_spend
    inner join accounts
        on accounts.platform = 'meta'
        and accounts.normalized_account_id = regexp_replace(staged_spend.account_id, '[^0-9]', '', 'g')
)

select 1
where not exists (
    select 1
    from joined
    where spend = 42
)
