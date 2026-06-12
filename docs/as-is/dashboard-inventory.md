# Dashboard Inventory

## Dashboard General MX

- Dashboard ID: `8e53eb82-587c-4b92-a0fa-0f6283677e28`
- Team ID: `1da677de-9313-4b49-9110-81a6b756ca7e`
- Team visible: `GLOMO`
- Fecha visible durante captura: `Today to 4:59AM CST`
- Navbar metrics observadas: `users`, `sessions`

## Tabs

| Tab | Nombre visible | Estado |
| --- | --- | --- |
| 0 | Resumen | Capturado |
| 1 | Errores | Detectado; requiere barrido especifico adicional |

## Cards visibles en Resumen

| Nombre visible | Link card id | Tipo visual observado |
| --- | --- | --- |
| Sesiones con conversion | `0e516955-e9b4-4374-952f-68a322692565` | KPI + timeseries |
| Tiempo medio de sesion | `0b133a6c-fc6f-42c2-bb39-f9e3cc50eb3a` | KPI + timeseries |
| Detalle por APP Name y Sistema operativo | `30fcc0db-fe32-46e7-9c8c-23479aaadd60` | Tabla |
| Paginas Vistas | `62865633-41aa-48c2-8ad4-4844b2ae2ef0` | Chart/card |
| Sesiones | `c86c5a4e-9c5f-436e-a298-99ad5ec81e34` | Chart/card |

## Analytics metadata observada

| Metadata cardId | cardType | viewName(s) | Uso |
| --- | --- | --- | --- |
| `9dd00685-ba64-4055-af56-3db4f8bc1c85` | CHART | `dimensionQuery`, `timeSeriesQuery`, `coreMetrics` y variantes `ComparisonSegment` | Chart/KPI/timeseries |
| `a239d190-f467-423f-8188-d06db73bc0f5` | TABLE | `topN`, `table:historical`, `coreMetrics:historical` | Tabla detalle por app/OS |
| n/a | n/a | `navbarMetricsQuery` | Navbar users/sessions |

## Filtros globales observados

- Team filter asociado a `teamID=1da677de-9313-4b49-9110-81a6b756ca7e`.
- Segmento global visible: `All data + segment`.
- Rango temporal global visible: `Today to 4:59AM CST`.
- Los filtros se materializan en `filter.arguments` dentro de los bodies de analytics.
