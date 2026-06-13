# SDS Quantum Metric

Aplicacion local para ingerir datos reales de Quantum Metric, guardarlos en Parquet por pais y visualizarlos offline mediante APIs locales.

[![CI develop](https://github.com/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/actions/workflows/ci.yml)
[![CI master](https://github.com/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/actions/workflows/ci.yml)

## Comandos

```bash
make setup
make run
make CI
make build
make kill
```

`make run` levanta backend FastAPI, frontend Vite y un visor desktop PyWebView. Las pantallas principales consumen solo APIs locales respaldadas por Parquet; Quantum se llama exclusivamente desde Test de conexion e Ingesta.

## Dashboard local

Home muestra `Dashboard General {pais}` y consume solo endpoints locales:

- `GET /api/analytics/countries`
- `GET /api/analytics/dashboard/summary`
- `GET /api/analytics/dashboard/summary/table`
- `GET /api/analytics/dashboard/errors`
- `GET /api/analytics/dashboard/errors/table`
- `GET /api/analytics/dimensions`
- `GET /api/analytics/segments`

Los widgets de Resumen se calculan desde `response_json.rows` en
`data/parquet/country=<pais>/raw_api_calls/*.parquet`. Se reconocen campos y aliases para
page views, sessions, converted sessions y average session duration. La tabla agrupa por
`app_name` y `operating_system`, o por la dimension activa cuando se selecciona una. Errores
agrega `sessions_with_error` y calcula `% sesiones con error` solo cuando existen sesiones o
porcentajes fuente.

Si faltan Parquet, filas parseables o campos de metrica, la API devuelve `status: "empty"` o
valores `null`; la UI no rellena datos falsos. Las dimensiones se infieren de
`request_json.dimensions`, `dimensionFills`, `metadata` y claves de filas. Los segmentos se
infieren de valores locales como app name, browser, operating system, plataforma, error y
conversion.

## Seguridad

Las cookies de Quantum se leen solo bajo demanda, se mantienen en memoria y no se persisten. El modo manual tambien mantiene la cookie solo en memoria.

Los endpoints de analytics offline no importan ni construyen `QuantumClient`, no usan Playwright
y no hacen llamadas `httpx` a internet. Para probarlo, ejecuta una ingesta, desconecta la red y
recarga Home: el dashboard debe seguir funcionando sobre Parquet local.

## Estado

- As-Is documentado en `docs/as-is`.
- Backend local versionado bajo `/api`.
- Persistencia Parquet en `data/parquet/country=<pais>`.
- Export/import ZIP en `data/exports`.
