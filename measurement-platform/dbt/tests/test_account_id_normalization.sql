with accounts as (
  select
    'meta' as platform,
    '1234567890' as account_id,
    regexp_replace('1234567890', '[^0-9]', '', 'g') as normalized_account_id
),

staging as (
  select
    'act_1234567890' as account_id
),

matches as (
  select 1
  from staging s
  inner join accounts a
    on a.platform = 'meta'
   and a.normalized_account_id = regexp_replace(s.account_id, '[^0-9]', '', 'g')
)

select 1
where not exists (select 1 from matches)
