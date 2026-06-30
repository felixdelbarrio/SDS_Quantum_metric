# Runbook - Datasets

Datasets lista paises con datos locales y entidades Parquet.

Cuando existe metadata de Iteracion 12:

- Las entidades se agrupan por dashboard.
- Cada entidad muestra `widget_id` o rol.
- Export incluye `config/quantum_config.json` y `config/dashboards.json`.

Import restaura la configuracion completa desde `quantum_config.json`.
