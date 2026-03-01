-- dim_geo — Geography dimension (from seed dim_geo_states or warehouse seed)
{{
  config(
    materialized='table',
    schema='marts'
  )
}}

select
  geo_id,
  geo_name,
  geo_type,
  country_code
from {{ ref('dim_geo_states') }}
