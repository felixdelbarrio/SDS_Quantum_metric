# Widget Inventory

## Navbar metrics

- Endpoint: `POST /analytics`
- `viewName`: `navbarMetricsQuery`
- Metrics count: 2
- Dimensions count: 0
- Pagination: `limit=0`, `offset=0`
- Respuesta: filas de users/sessions para navbar.

## KPI + timeseries cards

- Endpoints:
  - `POST /analytics`
  - `POST /analytics/historical`
- `viewName` observado:
  - `dimensionQuery`
  - `dimensionQueryComparisonSegment`
  - `timeSeriesQuery`
  - `timeSeriesQueryComparisonSegment`
  - `coreMetrics`
  - `coreMetricsComparisonSegment`
  - equivalentes con sufijo `:historical`
- Respuestas:
  - `/analytics`: `rows` actuales y `stats`.
  - `/analytics/historical`: filas historicas, `period`, `periodCount`, `statistics`.

## Table cards

- Endpoints:
  - `POST /analytics`
  - `POST /analytics/historical`
- `cardType`: `TABLE`
- `viewName` observado:
  - `topN`
  - `table:historical`
  - `coreMetrics:historical`
- Tabla visible:
  - Dimension principal: `name`
  - Columnas visibles: `Page Views`, `Sessions`, `General - Conversiones`.
- Paginacion observada:
  - Actual: `limit=12`, `offset=0`
  - Historico: `limit=30`, `offset=0`

## Controles de filtro

- `Add Dashboard Dimension`
- `Dashboard Segment`
- `All data + segment`
- Date picker global

Estos controles cambian `dimensions`, `filter`, `dimensionFills`, `pagination` y `metadata` en las llamadas de analytics.
