-- Ensure platform account joins tolerate provider-specific prefixes/separators.
with accounts as (
  select 'meta' as platform, '752736179021770' as account_id
),

staging as (
  select 'meta' as platform, 'act_752736179021770' as account_id
),

joined as (
  select s.account_id
  from staging s
  inner join accounts a
    on a.platform = s.platform
   and regexp_replace(a.account_id, '[^0-9]', '', 'g') = regexp_replace(s.account_id, '[^0-9]', '', 'g')
)

select 'account ids were not normalized before join' as failure
where not exists (select 1 from joined)
