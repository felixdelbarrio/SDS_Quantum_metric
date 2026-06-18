# Iteracion 8 Code Audit

## Resumen

La base actual ya tiene contratos visuales, progreso de ingesta, persistencia fuera del repo y smoke desktop. La deuda principal para cerrar producto esta en cuatro zonas: Dashboard aun mezcla informacion operacional, los periodos/ejes no estan normalizados, el almacenamiento sigue siendo por pais/rango en vez de particion diaria, y Configuracion/Datasets conservan acciones tecnicas que aumentan carga cognitiva.

## Dashboard

- `frontend/src/features/home/components/DashboardHeader.tsx` muestra `raw_calls`, `rows`, `cards` y `regression_status` dentro de `dataset-facts`; deben salir de Home.
- `DashboardHeader` mantiene boton `Actualizar` y prop `onRefresh`; la especificacion pide invalidacion automatica por cambio de pais/rango/dimension/segmento y finalizacion de ingesta.
- El estado vacio de `HomePage` tambien muestra `Actualizar`.
- El rango visible en `DashboardHeader` usa `YYYY-MM-DD`; no replica un label tipo Quantum Web.
- Las queries ya incluyen `startDate/endDate`, pero backend solo comprueba coincidencia con un periodo global, no consulta particiones diarias.

## Periodos, ejes y widgets

- `backend/app/quantum_dashboard/parsers.py::_line_chart_payload` y `_donut_chart_payload` siguen generando `period_label=None`.
- `backend/app/quantum_dashboard/builder.py::_period_label` puede devolver labels crudos como `1781676000 - 1781686680 CST`.
- `backend/app/quantum_dashboard/parsers.py::_short_ts_label` devuelve el texto numerico tal cual cuando recibe epoch.
- `QuantumChartTooltip` es solo `sr-only`; no hay tooltip real de hover/focus.
- `QuantumChart` no expone acciones de descarga CSV/SVG/PNG.
- Los paths estan memoizados, pero no hay puntos interactivos accesibles con teclado.

## Tabla App Name / Sistema Operativo

- `parsers.py::_expandable_summary_rows` agrupa por App Name, pero crea siempre hijos desde todas las filas de entrada.
- Si la respuesta web ya trae fila padre y filas hijas, puede duplicar la fila padre como hija o crear hija `Null`.
- Los deltas ya se parsean parcialmente, pero `SUMMARY_TABLE_ALIASES` no cubre todos los nombres posibles y el estado semantico se calcula solo por signo.
- `SummaryDetailTable.tsx` ya tiene chevron, search, sort y deltas, pero no tiene export CSV ni header sticky explicito del componente.

## Ingesta y almacenamiento

- `IngestionService` planifica chunks, salta rangos ya cubiertos y publica incrementalmente, pero `ParquetStore.merge_raw_calls` compacta en `country=MX/raw_api_calls`, no en `country=MX/day=YYYY-MM-DD/raw_api_calls`.
- Los derivados se escriben en `country=MX/derived/*`, no en particiones diarias.
- `LocalDashboardService.summary/errors/tables` llaman `_period(country)` y `_period_matches(...)`; si el rango no coincide con la ultima ingesta completa devuelve vacio.
- No existe `range_query.py` ni manifest `manifests/day_coverage.parquet`.
- No existe endpoint `/api/local-dashboard/coverage`.
- No existe endpoint `/api/ingestions/missing-days`.

## Configuracion Quantum

- `QuantumPage.tsx` muestra `Pais activo` en el bloque Browser/Sesion.
- `QuantumCountryConfig.enabled` sigue representando activo; negocio pide que todo pais configurado este activo y que exista un unico pais default.
- Los modelos no incluyen `QuantumDashboardConfig`, tabs ni widgets enable/disable.
- `POST /api/quantum/test-connection` prueba solo el pais activo, no pais por fila.
- `POST /api/quantum/discover-dashboard` actualiza dashboard/tab legacy, no una estructura dashboard-widget por pais.

## Datasets

- `DatasetsPage.tsx` conserva botones `Auditar`, `Regenerar derivados` y `Ejecutar regresion`.
- Datasets conserva KPIs de dashboard y tablas de negocio (`Apps principales`, `Errores principales`) que pertenecen a Home o regresion, no a consola de datos.
- La auditoria de entidades ya usa lectura paginada con `read_country_entity_page`.
- Import/export exporta Parquet por pais y `manifest.json`, pero no incluye configuracion completa (`quantum.json`, dashboards/widgets, schemas, regression metadata).
- No existe export CSV por entidad en UI.

## Seguridad y performance

- `scan_no_secrets.py` y Bandit ya forman parte de `make CI`.
- Import ZIP valida rutas `..` y paises del manifest, pero la ruta esperada es `parquet/...`; no cubre aun `config/`, `schemas/` ni `regression/`.
- Dashboard no llama endpoints RAW directamente, pero el backend puede leer datasets completos para agregaciones de tabla.

## Decision de Iteracion 8

- Introducir un modelo diario como canonico nuevo y migracion controlada desde datasets legacy cuando los rangos se puedan mapear a dias.
- Mantener solo compatibilidad temporal de lectura para import/migracion, no duplicar modelos vivos en la UI.
- Centralizar period labels y ticks en backend.
- Simplificar Home/Datasets antes de ampliar funcionalidad para reducir carga cognitiva.
- Hacer Configuracion dashboard-widget extensible sin persistir secretos ni cookies.
