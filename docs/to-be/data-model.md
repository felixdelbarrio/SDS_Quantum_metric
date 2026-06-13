# Data Model

## Raw calls

Dataset: `data/parquet/country=<country>/raw_api_calls/*.parquet`

Campos obligatorios para descubrir y leer llamadas:

- `ingestion_id`
- `ingestion_ts`
- `country`
- `source_endpoint`
- `http_method`
- `status_code`
- `dashboard_id`
- `card_id`
- `card_type`
- `view_name`
- `metric_ids`
- `query_hash`
- `response_hash`
- `request_json`
- `response_json`
- `row_count`

Campos opcionales usados cuando existen:

- `source_ts_start`
- `source_ts_end`

`request_json` debe contener la query Quantum sanitizada. El normalizador intenta leer:

- `metadata.dashboardId`
- `metadata.cardId`
- `metadata.cardType`
- `metadata.viewName`
- `metadata.metricIds`
- `dimensions.dimensions`
- `dimensionFills.dimensionFills`
- `metrics.metrics`

`response_json` debe ser JSON sanitizado. La fuente principal es `response_json.rows`. Para
compatibilidad legacy tambien se leen filas tipo array si hay `columns` o `columnNames`.

Metricas reconocidas por aliases:

- `page_views`
- `sessions`
- `converted_sessions`
- `avg_session_time`
- `sessions_with_error`
- `error_session_percent`
- deltas historicos como `page_views_delta_percent` y `conversions_delta_percent`

Dimensiones reconocidas por aliases:

- `app_name`
- `operating_system`
- `application_type`
- `application_version`
- `browser`
- `ai_detected`
- `active_fix`
- `active_test`
- `platform`
- `device_type`

Si una metrica no existe en Parquet, la API no inventa valores: devuelve widget con
`missing_source_field` o estado `empty` cuando no hay ninguna metrica util.

## Manifests

Dataset: `data/manifests/ingestion_manifest.parquet`

Incluye estado, fechas, pais, conteos, errores sanitizados y duracion.

## Datasets derivados

La version actual deriva en memoria desde `raw_api_calls` para evitar duplicados y mantener
compatibilidad con Parquet existente. Si se persisten derivados, deben vivir bajo:

- `data/parquet/country=<country>/derived/dashboard_summary/`
- `data/parquet/country=<country>/derived/dashboard_summary_table/`
- `data/parquet/country=<country>/derived/dashboard_errors/`
- `data/parquet/country=<country>/derived/dashboard_errors_table/`
- `data/parquet/country=<country>/derived/dimensions/`
- `data/parquet/country=<country>/derived/segments/`

Cada fila derivada debe incluir claves de evidencia como `ingestion_id`, `ingestion_ts`,
`source_card_id`, `source_dashboard_id`, `source_metric_ids`, `source_query_hash`,
`source_response_hash`, `derived_schema_version`, `metric_name`, `dimension_name`,
`dimension_value`, `period_start`, `period_end`, `value`, `unit` y `raw_evidence_path`.
