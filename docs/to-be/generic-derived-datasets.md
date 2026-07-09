# Generic Derived Datasets

Iteration 17 anade datasets dashboard-driven para evitar acoplamiento a summary/errors.

## Datasets

| Dataset | Contenido |
|---|---|
| `derived/dashboard_tabs` | Tabs reales por dashboard/rango |
| `derived/dashboard_widgets` | Widgets listos para Home agrupables por tab |
| `derived/widget_chart_payloads` | Payload grafico por widget generico o especifico |
| `derived/widget_table_payloads` | Filas/columnas de tablas genericas |

Los datasets se escriben bajo:

```text
parquet/country=<pais>/range_key=<range>/derived/...
```

Para `today` se mantiene publicacion legacy por compatibilidad.

## Lectura

`LocalDashboardService.dashboard()` lee primero `derived/dashboard_widgets`. Si no existe, cae a los datasets legacy de summary/errors para no romper datos antiguos.
