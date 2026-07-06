# Runbook - Datasets

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
