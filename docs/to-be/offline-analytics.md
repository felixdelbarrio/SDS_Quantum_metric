# Offline Analytics

Las APIs locales leen Parquet:

- `GET /api/datasets`
- `GET /api/dashboards`
- `GET /api/cards/{card_id}/data`
- `GET /api/analytics/summary`
- `GET /api/analytics/timeseries`
- `GET /api/analytics/table`
- `GET /api/analytics/filters`

El frontend no llama dominios Quantum en Home, Dashboards, Datasets o Analytics.
