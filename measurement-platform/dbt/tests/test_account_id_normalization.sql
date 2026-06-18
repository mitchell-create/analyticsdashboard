-- Ensures account ID normalization handles provider prefixes like `act_`.
-- This protects the fact_spend_daily account join from silently dropping spend rows.
with accounts(platform, account_id) as (
  values
    ('meta', '752736179021770'),
    ('google', '3286876149'),
    ('tiktok', '6852902925644070917')
),
source_rows(platform, raw_account_id) as (
  values
    ('meta', 'act_752736179021770'),
    ('google', '3286876149'),
    ('tiktok', '6852902925644070917')
),
joined as (
  select
    s.platform,
    s.raw_account_id,
    a.account_id as mapped_account_id
  from source_rows s
  left join accounts a
    on a.platform = s.platform
    and regexp_replace(a.account_id, '[^0-9]', '', 'g') = regexp_replace(s.raw_account_id, '[^0-9]', '', 'g')
)
select *
from joined
where mapped_account_id is null
