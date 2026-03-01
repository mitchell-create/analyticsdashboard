# dbt tests

- Run **dbt run** first to build models; then run **dbt test**.
- **dim_geo** is a model (not the seed): you must run the dim_geo model so the table exists before testing it.
- To build and test the models you have so far (Shopify + geo):
  ```
  dbt run --select stg_shopify_orders fact_kpi_daily dim_geo
  dbt test --select fact_kpi_daily dim_geo
  ```
- Once you add more sources and build other models, run **dbt test** with no selector to run all tests.
