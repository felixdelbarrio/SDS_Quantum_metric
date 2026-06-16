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

## Configuracion Quantum

La app configura Quantum por pais con una pantalla funcional: browser, modo de sesion, pais activo,
Base URL, apariencia y acciones de guardar, test, descubrir dashboard y validar acceso.

Dashboard ID, Team ID, tabs, card IDs y hashes no se muestran al usuario. Se resuelven internamente
desde `.env`, configuracion local o URL de Quantum Web cuando es posible.

`.env.example` incluye Mexico. Para Espana, Colombia, Argentina o Peru se anade una fila en
Quantum y, al guardar, la configuracion queda sincronizada en `QM_COUNTRY_CONFIGS` dentro de
`.env`. Las cookies de navegador o manuales no se escriben en disco.

## Dashboard local

Home muestra `Dashboard General {pais}` y consume solo endpoints locales:

- `GET /api/local-dashboard/countries`
- `GET /api/local-dashboard/status`
- `GET /api/local-dashboard/summary`
- `GET /api/local-dashboard/summary/table`
- `GET /api/local-dashboard/errors`
- `GET /api/local-dashboard/errors/top-errors`
- `GET /api/local-dashboard/errors/app-name`

La ingesta captura tabs `Resumen` y `Errores`, persiste raw API calls, construye contratos visuales,
snapshots web, datasets derivados y ejecuta regresion Web vs Local. Home solo pinta datos derivados
con regresion `passed` o `passed_with_tolerance`.

Si hay raw calls pero faltan cards obligatorias, derivados o regresion, la API devuelve un motivo
accionable. La UI no rellena datos falsos ni oculta discrepancias.

## Seguridad

Las cookies de Quantum se leen solo bajo demanda, se mantienen en memoria y no se persisten. El modo manual tambien mantiene la cookie solo en memoria.

Los endpoints de analytics offline no importan ni construyen `QuantumClient`, no usan Playwright
y no hacen llamadas `httpx` a internet. Para probarlo, ejecuta una ingesta, desconecta la red y
recarga Home: el dashboard debe seguir funcionando sobre Parquet local.

## Estado

- As-Is documentado en `docs/as-is`.
- Contratos de dashboard en `docs/to-be/local-dashboard-contract.md`.
- Datasets derivados en `docs/to-be/parquet-derived-datasets.md`.
- Regresion en `docs/regression/latest-web-vs-local.md`.
- Backend local versionado bajo `/api`.
- Persistencia Parquet en `data/parquet/country=<pais>`.
- Export/import ZIP en `data/exports`.
