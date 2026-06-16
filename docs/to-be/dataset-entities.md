# Dataset Entities

Entidades auditables por pais:

- `raw_api_calls`
- `visual_contracts`
- `dashboard_cards`
- `web_snapshots`
- `derived/summary_widgets`
- `derived/summary_detail_table`
- `derived/errors_widgets`
- `derived/errors_top_errors_table`
- `derived/errors_app_name_table`
- `derived/timeseries`
- `derived/chart_payloads`
- `regression/web_vs_local_results`
- `regression/discrepancies`

Endpoints:

- `GET /api/datasets/{country}/entities`
- `GET /api/datasets/{country}/entities/{entity}`
- `GET /api/datasets/{country}/entities/{entity}/schema`
- `POST /api/datasets/export`
- `POST /api/datasets/import`
- `DELETE /api/datasets/{country}?confirm={country}`

Las respuestas de filas estan paginadas con `offset` y `limit`, con limite maximo de 500 filas por request.
