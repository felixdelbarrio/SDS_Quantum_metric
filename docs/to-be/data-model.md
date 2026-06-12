# Data Model

## Raw calls

Dataset: `data/parquet/country=<country>/raw_api_calls/*.parquet`

Campos principales:

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

## Manifests

Dataset: `data/manifests/ingestion_manifest.parquet`

Incluye estado, fechas, pais, conteos, errores sanitizados y duracion.
