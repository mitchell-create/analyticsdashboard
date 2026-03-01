-- stg_metricool_tiktok — Staging for Metricool TikTok organic daily metrics
-- Adjust source table and column names to match your Metricool sync.

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

with source as (
  select * from {{ source('raw_metricool', 'metricool_tiktok_daily') }}
),

renamed as (
  select
    (report_date::date) as report_date,
    coalesce(views::bigint, 0) as views,
    likes::bigint as likes,
    comments::bigint as comments,
    shares::bigint as shares,
    followers::bigint as followers
  from source
)

select * from renamed
