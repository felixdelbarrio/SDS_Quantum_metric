# Dashboard Card Map

Mandatory visual roles for `Dashboard General MX`:

| Tab | Role | Local title | Parser |
| --- | --- | --- | --- |
| Resumen | `summary.page_views` | Paginas vistas | `timeseries_metric_card_v1` |
| Resumen | `summary.sessions` | Sesiones | `timeseries_metric_card_v1` |
| Resumen | `summary.converted_sessions` | Sesiones con conversion | `timeseries_metric_card_v1` |
| Resumen | `summary.avg_session_duration` | Tiempo medio de sesion | `timeseries_metric_card_v1` |
| Resumen | `summary.detail_by_app_name_os` | Detalle por APP Name y Sistema operativo | `dimension_table_card_v1` |
| Errores | `errors.error_sessions_percentage_evolution` | Evolutivo - % Sesiones con Error | `timeseries_metric_card_v1` |
| Errores | `errors.top_errors_by_error_name` | Top 10 Errores por nombre del error | `top_errors_table_card_v1` |
| Errores | `errors.error_sessions_by_app_name_comparison` | Comparativa de sesiones con error por App Name | `donut_distribution_card_v1` |
| Errores | `errors.error_session_percentage_by_app_name` | % Sesiones con Error por App Name | `percentage_table_card_v1` |

Card mapping priority:

1. Explicit `card_role` or `visualRole` metadata.
2. Known Quantum metadata fields such as `cardTitle`, `cardType`, `metricIds`.
3. Title/metric hints for the mandatory catalog.

If a mandatory role cannot be mapped, ingestion/regeneration records `failed_missing_card` and Home shows an actionable readiness reason instead of an empty dashboard.
