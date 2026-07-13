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

La app configura Quantum por pais con una pantalla funcional: browser, modo de sesion,
Base URL, pais por defecto, descubrimiento real por pais, dashboards por pais,
widgets con ID/tipo/enabled, apariencia, profundidad de ingesta y accion de guardar.
Desde Iteracion 14 la pantalla se guia por un unico pais seleccionado; cambiar el combo
de pais cambia dashboards, estructura y widgets visibles.

Dashboard ID, Team ID, tabs, widget IDs y tipos se muestran cuando forman parte de la
configuracion auditable. La lista de dashboards sale de Quantum Web mediante GraphQL
`resourcesList` y los tabs/widgets del dashboard seleccionado salen de `LoadDashboard`.
La lista se cachea localmente por pais para uso offline hasta pulsar `Actualizar dashboards`.
Los dashboards manuales pueden darse de alta por URL o ID y se validan contra Quantum antes
de ser default.
La app no crea widgets por defecto ni permite guardar un pais activo sin dashboard default.

`.env.example` incluye Mexico. Para Espana, Colombia, Argentina o Peru se anade una fila en
Quantum y, al guardar, la configuracion principal queda en `config/quantum_config.json`.
La sincronizacion `.env` solo incluye valores operativos no secretos. Las cookies de navegador
o manuales no se escriben en disco.

## Dashboard local

Home muestra `Dashboard General {pais}` y consume solo endpoints locales. Desde Iteración 18,
el endpoint principal reproduce contratos schema 3 desde `derived/widget_contracts` con jerarquía
Dashboard → Tab → Section → Widget:

- `GET /api/local-dashboard/countries`
- `GET /api/local-dashboard/dashboard`
- `GET /api/local-dashboard/status`
- `GET /api/local-dashboard/summary`
- `GET /api/local-dashboard/summary/table`
- `GET /api/local-dashboard/errors`
- `GET /api/local-dashboard/errors/top-errors`
- `GET /api/local-dashboard/errors/app-name`
- `GET /api/local-dashboard/cards/{card_role}/detail`
- `GET /api/local-dashboard/cards/{card_role}/breakdown`
- `GET /api/local-dashboard/cards/{card_role}/points`

La ingesta captura tabs/secciones reales, persiste raw API calls, construye el contrato canónico,
snapshots web, vistas derivadas y ejecuta regresión Web vs Local. Home pinta
`/api/local-dashboard/dashboard` exclusivamente desde el contrato canónico; no cae a Summary,
Errors o `dashboard_widgets`. Un dataset anterior exige nueva ingesta.

La ingesta publica particiones diarias `parquet/country=<pais>/day=YYYY-MM-DD/raw_api_calls`
y `parquet/country=<pais>/manifests/day_coverage.parquet`. Home consulta
`/api/local-dashboard/coverage` y puede lanzar `/api/ingestions/range` para capturar exactamente
el periodo visible sin bloquear la navegacion. La pagina Ingesta usa la profundidad por defecto
configurada y etiqueta esa captura como `range_key=default`; Home usa `today`, `yesterday`,
`last_7_days` o `custom` segun el selector.

Desde Iteracion 10, Today, Yesterday y Last 7 Days se consultan y persisten con `range_key`.
Los widgets no agregables desde dias sueltos requieren contrato Quantum capturado para la ventana
completa. Si no existe contrato del rango, Home muestra estado accionable y no reutiliza datos de
otro preset.

Las gráficas se renderizan desde `QuantumChartContract`: tipo, ejes, labels, orden de series,
baseline, bandas, anomaly, leyenda y periodo salen de Quantum. React no renombra series ni
regenera el periodo. Los valores usan `formatted`/`precision`; las tablas usan labels persistidos.

Si hay raw calls pero faltan cards obligatorias, derivados, cobertura o regresion, la API devuelve
un motivo accionable. La UI no rellena datos falsos, no oculta discrepancias y envia el detalle
tecnico a Datasets/Evidence.

## Datasets

Datasets permite ver entidades Parquet por pais: RAW calls, contratos visuales, snapshots,
derivados, chart payloads y regresion. Las entidades se agrupan por categoria, dashboard y
widget, se leen paginadas, tienen cabeceras fijas y CSV por entidad. El ZIP de export/import
incluye datos, `config/quantum_config.json` y `config/dashboards.json` sin secretos. La exportacion se escribe en la ruta
configurada por el usuario, por defecto `~/Downloads`, y la UI muestra la ruta exacta creada por
backend.
El borrado exige confirmacion exacta del pais.

Por defecto los datos viven en la ruta persistente del usuario calculada con `platformdirs`. `QM_DATA_DIR` queda reservado como override explicito. Si se detecta `./data` legacy, Datasets muestra aviso y permite migrarlo.

## Seguridad

El modo de sesion por defecto reutiliza las cookies del Chrome activo. La captura se ejecuta con
el Chromium headless empaquetado, sin abrir ventanas, perfiles ni sesiones adicionales de Chrome.
El modo manual mantiene la cookie solo en memoria.

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
- Cierre Iteracion 8 en `docs/to-be/iteration-8-product-finish.md`.
- Modelo diario en `docs/to-be/daily-parquet-model.md`.
- Faltantes async en `docs/to-be/missing-days-ingestion.md`.
- Import/export en `docs/to-be/export-import-contract.md`.
- Contrato de rangos en `docs/to-be/iteration-10-range-contract-model.md`.
- Reglas de agregacion por rango en `docs/to-be/quantum-range-aggregation-rules.md`.
- Hardening Chrome en `docs/to-be/chrome-session-hardening.md`.
- Export a Downloads en `docs/to-be/export-downloads-contract.md`.
- Descubrimiento de dashboards en `docs/to-be/iteration-12-dashboard-discovery.md`.
- Fix de descubrimiento real en `docs/to-be/iteration-13-dashboard-discovery-fix.md`.
- API de dashboards por pais en `docs/to-be/dashboard-list-api-contract.md`.
- Resources GraphQL en `docs/to-be/graphql-dashboard-resources-contract.md`.
- Configuracion Iteracion 14 en `docs/to-be/iteration-14-wow-configuration.md`.
- RCA Iteracion 15 en `docs/as-is/iteration-15-critical-rca.md`.
- Hardening Iteracion 15 en `docs/to-be/iteration-15-critical-fix-design.md`.
- Dashboards manuales en `docs/to-be/manual-dashboard-contract.md`.
- Tabs/widgets reales en `docs/to-be/dashboard-tabs-widgets-contract.md`.
- Contrato de dashboards en `docs/to-be/dashboard-discovery-contract.md`.
- Contrato de tabs/widgets en `docs/to-be/dashboard-structure-contract.md`.
- Default por dashboard en `docs/to-be/config-dashboard-default.md`.
- Datasets multi-dashboard en `docs/to-be/multi-dashboard-datasets.md`.
- Iteracion 9 storage audit en `docs/as-is/iteration-9-storage-audit.md`.
- Iteracion 9 RCA de ingesta en `docs/as-is/iteration-9-ingestion-failure-rca.md`.
- Evidencia Web/Local en `docs/to-be/web-local-evidence-chain.md`.
- RCA Iteracion 16 en `docs/as-is/iteration-16-widget-support-rca.md`.
- Soporte generico de widgets en `docs/to-be/iteration-16-widget-support-refactor.md`.
- Contrato de parsers genericos en `docs/to-be/generic-widget-parser-contract.md`.
- Validacion Colombia SDS en `docs/to-be/colombia-sds-validation.md`.
- Recuperacion Mexico last 7 days en `docs/to-be/mexico-regression-recovery.md`.
- Estados de ingesta Iteracion 16 en `docs/to-be/ingestion-failure-states.md`.
- Regresion CO/MX Iteracion 16 en `docs/regression/iteration-16-*-last-7-days.md`.
- RCA Iteracion 17 en `docs/as-is/iteration-17-dashboard-driven-rca.md`.
- Arquitectura dashboard-driven en `docs/to-be/iteration-17-dashboard-driven-architecture.md`.
- Tabs dinamicas en `docs/to-be/dynamic-tabs-contract.md`.
- Render generico de dashboards en `docs/to-be/generic-dashboard-rendering.md`.
- Cobertura de rangos en `docs/to-be/coverage-contract.md`.
- Bloqueo de scopes de ingesta en `docs/to-be/ingestion-scope-locking.md`.
- Datasets genericos dashboard-driven en `docs/to-be/generic-derived-datasets.md`.
- Regresion CO/MX Iteracion 17 en `docs/regression/iteration-17-*-last-7-days.md`.
- Contrato canónico Iteración 18 en `docs/to-be/iteration-18-canonical-widget-contract.md`.
- Auditoría live Iteración 18 en `docs/as-is/iteration-18-quantum-widget-contract-audit.md`.
- Regresiones CO/MX Iteración 18 en `docs/regression/iteration-18-*-last-7-days.*` (BLOCKED hasta autenticación real).
- Backend local versionado bajo `/api`.
- Persistencia Parquet en la ruta de usuario activa bajo `parquet/country=<pais>`.
- Export/import ZIP en la ruta de usuario activa bajo `exports`.
