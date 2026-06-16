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

`make run` levanta backend FastAPI, frontend Vite y un visor desktop PyWebView. Las pantallas principales consumen solo APIs locales respaldadas por Parquet; Quantum se llama exclusivamente desde ingesta y descubrimiento interno.

`make CI` tambien compila el frontend y ejecuta un smoke desktop preflight. `make build` valida el frontend empaquetado y el servidor local antes de generar el binario.

## Configuracion Quantum

La app configura Quantum por pais con una pantalla funcional: browser, modo de sesion, pais activo,
Base URL, apariencia, profundidad de ingesta y accion de guardar.

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
- `GET /api/local-dashboard/cards/{card_role}/detail`
- `GET /api/local-dashboard/cards/{card_role}/breakdown`
- `GET /api/local-dashboard/cards/{card_role}/points`

La ingesta captura tabs `Resumen` y `Errores`, persiste raw API calls, construye contratos visuales,
snapshots web, datasets derivados y ejecuta regresion Web vs Local. Home solo pinta datos derivados
con regresion `passed` o `passed_with_tolerance`.

Las graficas se renderizan desde `chart_payload`: ejes, leyenda, series Mobile/Desktop, bandas y periodo salen del backend y se persisten en `derived/chart_payloads`. React no fabrica curvas desde agregados.

Si hay raw calls pero faltan cards obligatorias, derivados o regresion, la API devuelve un motivo
accionable. La UI no rellena datos falsos ni oculta discrepancias.

## Datasets

Datasets permite auditar entidades Parquet por pais: RAW calls, contratos visuales, snapshots, derivados, chart payloads y regresion. Las entidades se leen paginadas y pueden exportarse/importarse por ZIP. El borrado exige confirmacion exacta del pais.

Por defecto los datos viven en la ruta persistente del usuario calculada con `platformdirs`. `QM_DATA_DIR` queda reservado como override explicito. Si se detecta `./data` legacy, Datasets muestra aviso y permite migrarlo.

## Seguridad

Las cookies de Quantum se leen solo bajo demanda, se mantienen en memoria y no se persisten. El modo manual tambien mantiene la cookie solo en memoria.

La aplicacion local no implementa reproduccion, descarga, cache ni rutas de video de sesiones.

Los endpoints de analytics offline no importan ni construyen `QuantumClient`, no usan Playwright
y no hacen llamadas `httpx` a internet. Para probarlo, ejecuta una ingesta, desconecta la red y
recarga Home: el dashboard debe seguir funcionando sobre Parquet local.

## Estado

- As-Is documentado en `docs/as-is`.
- Contratos de dashboard en `docs/to-be/local-dashboard-contract.md`.
- Datasets derivados en `docs/to-be/parquet-derived-datasets.md`.
- Regresion en `docs/regression/latest-web-vs-local.md`.
- Contrato grafico en `docs/to-be/chart-contract.md`.
- Hardening desktop en `docs/to-be/desktop-packaging.md`.
- Ruta persistente en `docs/to-be/persistent-data-dir.md`.
- Progreso de ingesta en `docs/to-be/ingestion-progress.md`.
- Entidades auditables en `docs/to-be/dataset-entities.md`.
- Backend local versionado bajo `/api`.
- Persistencia Parquet en la ruta de usuario activa bajo `parquet/country=<pais>`.
- Export/import ZIP en la ruta de usuario activa bajo `exports`.
