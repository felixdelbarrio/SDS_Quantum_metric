# API Catalog

## `GET https://bbvamx.quantummetric.com/data/init`

- Funcion: bootstrap inicial y estado de sesion.
- Requiere cookie: si.
- Headers relevantes: cookies de `bbvamx.quantummetric.com`.
- Respuesta observada: HTTP 200 JSON.
- Claves: `accessToken`, `clientId`, `homeUri`, `iamIssuer`, `isUserAuthenticated`, `isVisibleAuthenticated`, `qmServicesEndpoint`, `redirectUri`, `subscription`, `tenantId`.
- Uso local: test de conexion y descubrimiento de `qmServicesEndpoint`.
- Persistencia: no persistir tokens; solo guardar metadatos no sensibles si se necesita auditoria.

## `GET https://bbvamx.quantummetric.com/auth-token`

- Funcion: renovacion/lectura de tokens para llamadas API.
- Requiere cookie: si.
- Respuesta observada: HTTP 200 JSON.
- Claves sensibles: `accessToken`, `refreshToken`, `qmVisible.accessToken`.
- Uso local: obtener Bearer token en memoria.
- Persistencia: prohibida.

## `POST https://api.quantummetric.com/query`

- Funcion: GraphQL operativo para permisos, recursos, teams, preferencias y metadatos.
- Requiere Bearer: si.
- Headers:
  - `Content-Type: application/json`
  - `Authorization: Bearer <accessToken>`
- Ejemplo validado:
  - Body: `{"query":"query { permissions { id handle accessLevel } }"}`
  - Resultado: HTTP 200, `data.permissions`, 76 elementos.
- Otros usos observados:
  - `currentMember`
  - `userPreferences`
  - `team`
  - `teamAppliedFilters`
  - `resource`
  - `listDigitalProperties`
- Persistencia: catalogos de dashboards, cards, filtros y permisos no sensibles.

## `POST https://bbvamx.quantummetric.com/api/graphql`

- Funcion: GraphQL legacy same-origin para reports/autosuggest y modulos concretos.
- Requiere cookie: si.
- Headers:
  - `Content-Type: application/json`
- Respuesta observada: HTTP 200 con `data` y, en un caso, `errors`.
- Uso local: catalogo complementario si un dashboard/report lo requiere.

## `POST https://bbvamx.quantummetric.com/analytics`

- Funcion: datos actuales para navbar, charts, tablas y core metrics.
- Requiere autenticacion: si.
- Headers observados:
  - `Content-Type: application/json`
  - `render-app: false`
  - `qm-visible: false`
  - `Authorization: Bearer <accessToken>` en llamadas desde worker.
- Body observado:
  - Top-level keys: `id`, `namespace`, `collections`, `relationships`, `dimensions`, `metrics`, `filter`, `pagination`, `ordering`, `dimensionFills`, `metadata`.
  - `metadata`: `dashboardId`, `cardId`, `cardType`, `viewName`, `pathName`, `metricIds`, `slowQuery`.
  - Paginacion: `limit`, `offset`.
- Respuesta observada: HTTP 200 JSON.
- Respuesta keys: `id`, `metadata`, `namespace`, `processed`, `project`, `rows`, `stats`.
- Persistencia Parquet:
  - `raw_api_calls`
  - `cards`
  - `metrics`
  - `derived`

## `POST https://bbvamx.quantummetric.com/analytics/historical`

- Funcion: historicos de charts, tablas y core metrics.
- Requiere autenticacion: si.
- Headers observados:
  - `Content-Type: application/json`
  - `render-app: false`
  - `qm-visible: false`
  - `x-query-id`
  - `Authorization: Bearer <accessToken>`
- Body observado:
  - Top-level keys: `query`, `ts`, `historicalRequest`.
  - `query` tiene la misma estructura Wren que `/analytics`.
  - `historicalRequest`: `statistics`, `period`, `periodCount`.
  - `ts`: par `[start_ts, end_ts]`.
- Respuesta observada: HTTP 200 JSON con filas historicas.
- Persistencia Parquet:
  - `raw_api_calls`
  - `historical`
  - `derived.timeseries`

## Configuracion

- `GET /configuration/crypto`
- `GET /configuration/crypto/diffs/production/default`
- `GET /configuration/replay`
- `GET /configuration/outboundLinks`
- `GET /configuration/capture`
- `GET /configuration/privacy`
- `GET /configuration/event`
- `GET /configuration/event/diffs/production/default`

Estos endpoints alimentan configuracion de captura, privacidad, eventos, replay y cifrado. Deben catalogarse para filtros/eventos, pero no son la fuente principal de analitica.
