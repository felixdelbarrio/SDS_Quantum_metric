# Runbook - Datasets

## Iteración 18: dataset canónico

Para Home, inspeccionar exclusivamente `range_key=<range>/derived/widget_contracts`. Verificar
`dashboard_id`, tab/section/widget, hashes, `parse_status` y timezone antes de analizar payloads.
`summary_*`, `errors_*` y `dashboard_widgets` son vistas legacy y no demuestran paridad de Home.
Si solo existen schemas anteriores, borrar/reingerir desde la UI; no mezclar rangos o dashboards.

Datasets lista paises con datos locales y entidades Parquet.

Cuando existe metadata de Iteracion 12:

- Las entidades se agrupan por dashboard.
- Cada entidad muestra `widget_id` o rol.
- Export incluye `config/quantum_config.json` y `config/dashboards.json`.

Import restaura la configuracion completa desde `quantum_config.json`.

Endpoints utiles:

- `GET /api/datasets/{country}/dashboards`
- `GET /api/datasets/{country}/entities?dashboard_id=...`
- `GET /api/datasets/{country}/entities/{entity}?dashboard_id=...&widget_id=...`

Para auditar Iteracion 15, filtrar siempre por `country`, `dashboard_id`, `widget_id` y `range_key` antes de comparar Colombia y Mexico.

Para auditar Iteracion 16:

- Revisar `range_key=last_7_days/derived/summary_widgets` y `derived/errors_widgets` para widgets genericos.
- Las tablas genericas se persistiran dentro del widget con `chart_type=table`, `table_columns` y `table_rows`.
- Comparar `source_query_hash` y `source_response_hash` por widget cuando una fila no cuadre con Quantum Web.
