# Architecture

## Componentes

- `backend`: FastAPI, Pydantic v2, cliente Quantum aislado, orquestador de ingesta, almacenamiento Parquet y analitica local.
- `frontend`: React + TypeScript + Vite, TanStack Query, Zustand, React Router y sistema de diseno centralizado.
- `desktop`: PyWebView para dar experiencia integrada.
- ruta persistente de usuario: Parquet, manifests, catalogo, exports y logs.

## Analitica local

La capa `backend/app/analytics` centraliza el dashboard offline:

- `models.py`: contratos Pydantic de paises, widgets, tablas, dimensiones, segmentos y estados vacios.
- `query_engine.py`: lectura de Parquet, filtrado, ordenacion y agregaciones.
- `normalizer.py`: parseo tolerante de `request_json` y `response_json`.
- `dimensions.py`: agrupacion de dimensiones inferidas.
- `segments.py`: segmentos aplicables desde valores locales.
- `errors.py`: calculo compartido de sesiones con error y porcentaje.

El motor lee entidades Parquet locales. Desde Iteracion 8, la cobertura y la ingesta incremental
prefieren particiones `parquet/country=<pais>/day=YYYY-MM-DD/raw_api_calls/*.parquet` y el
manifest `parquet/country=<pais>/manifests/day_coverage.parquet`. No usa `QuantumClient`,
Playwright ni clientes HTTP externos.

## Dashboard Quantum por cards

`backend/app/quantum_dashboard` implementa la capa canonica RAW -> contrato visual -> derivados:

- `catalog.py`: catalogo obligatorio de nueve roles visuales para Resumen y Errores.
- `discovery.py`: resolucion interna de dashboard, team y tabs desde `.env`, config o URL.
- `dashboard_discovery.py`: descubrimiento/cache de dashboards por pais desde payloads reales de Quantum Web.
- `dashboard_resources.py`: contrato paginado `resourcesList`, cache offline por pais y parsing de recursos dashboard.
- `dashboard_structure.py`: normalizacion de tabs, widgets, card IDs y tipos por dashboard.
- `manual_dashboard.py`: parseo y validacion de dashboards manuales por URL o dashboard ID.
- `capture.py`: captura guiada de tabs configuradas, con rango `ts` explicito y fallo solo si todas quedan sin analytics.
- `card_mapper.py`: asociacion de llamadas Quantum a roles visuales.
- `parsers.py`: estrategias por rol visual, con `chart_payload` cuando la respuesta trae puntos.
- `builder.py`: raw calls -> visual contracts -> web snapshots -> derived Parquet -> chart payloads.
- `service.py`: endpoints `/api/local-dashboard/*` desde derivados.
- `regression.py`: comparacion Web vs Local de valores, ejes, leyendas, series y tablas.
- `range_query.py`: resolucion de rangos y cobertura con severidad por preset.
- `aggregation_rules.py`: reglas canonicas para decidir si un widget puede agregarse o requiere contrato Quantum del rango completo.
- `evidence.py`: trazabilidad widget a widget desde Web snapshot hasta API local.

## Flujo de ingesta

1. El usuario lanza una ingesta desde la seccion Ingesta.
2. Se abre un contexto Playwright efimero con cookies en memoria.
3. Se resuelve el dashboard default del pais desde configuracion.
4. Se navegan las tabs configuradas con `ts=<range_key>` cuando aplica.
5. Se capturan respuestas reales de `/analytics` y `/analytics/historical`.
6. Se guardan raw calls normalizadas, particiones diarias y manifests en Parquet dentro de la ruta persistente.
7. Se generan contratos visuales, snapshots web, datasets derivados y `derived/chart_payloads`.
8. Se ejecuta regresion Web vs Local solo para widgets soportados y habilitados.
9. La ingesta solo termina `completed` si la regresion pasa; fallos de sesion, dashboard, widgets, analytics y cancelacion usan estados accionables.

La politica de rango usa `QUANTUM_INGESTION_DEPTH_DAYS` como Profundidad por defecto del boton `Ingestar`, mas `QUANTUM_INCREMENTAL_REPROCESS_DAYS` y `QUANTUM_INGESTION_CHUNK_DAYS`. El planner divide ventanas largas en chunks y el rewriter aplica el rango activo a payloads Quantum antes de persistir.
Cuando la UI solicita Today, Yesterday o Last 7 Days, la ingesta crea un contrato explicito con
`range_key`, `range_start`, `range_end`, `range_timezone` y `capture_mode=range_contract`.
Cada response se valida tras la reescritura temporal; si el rango extraido no coincide, no se
publica como dato local valido.

## Flujo del dashboard offline

1. Home llama `/api/local-dashboard/countries` para elegir pais por defecto.
2. El backend comprueba contratos, derivados, coverage diario y regresion.
3. Summary y Errors se sirven desde `derived/*`.
4. Search y sort operan sobre Parquet derivado local.
5. Si falta una card obligatoria, falla regresion o faltan dias, se devuelve error accionable.
6. El contrato local no expone Dimension/Segment: no hay botones, endpoints publicos de seleccion ni campos `applied_*` en `/api/local-dashboard/*`.

## Contrato grafico

Las cards graficas no se renderizan desde agregados. Backend persiste `ChartPayload` con ejes, ticks, series, leyenda, bandas y periodo. Frontend pinta ese payload con SVG; el modo Linea usa `path` suavizado y el modo Barras usa `rect` reales sobre los mismos puntos. Si falta el contrato, se muestra fallo contractual y regresion falla con estados especificos.

## Datasets Auditables

Datasets expone entidades Parquet por pais mediante `/api/datasets/{country}/entities` y `/api/datasets/{country}/entities/{entity}`. Las entidades incluyen categoria, dashboard ID, dashboard name, widget ID y widget role. Las respuestas son paginadas; RAW completo solo se lee bajo demanda. Export/import incluye `config/quantum_config.json`, `config/dashboards.json` y datos Parquet, rechazando secretos y rutas peligrosas. `/api/datasets/{country}/evidence` expone la cadena Web -> RAW -> derived -> API.

Los derivados por rango se guardan bajo `parquet/country=<pais>/range_key=<range>/derived`.
`today` conserva tambien la publicacion legacy para compatibilidad, pero los endpoints locales
filtran por `range_key` cuando se consulta un preset.

## Configuracion persistente

`backend/app/quantum/config_store.py` escribe `config/quantum_config.json` de forma atomica con schema version. El modelo contiene paises, dashboards, widgets, tema, browser, modo de sesion y profundidad de ingesta. Cookies y Authorization nunca se persisten.

La lista offline de recursos dashboard vive en `config/dashboard_resources/<country>.json`.
El cache guarda IDs, nombres, tipo, starred, source y timestamps; no guarda cookies ni
Authorization. `POST /api/quantum/countries/{country}/dashboards/refresh` fuerza Quantum
GraphQL y `GET /api/quantum/countries/{country}/dashboards` lee cache/config local.

Cada pais activo requiere un dashboard default validado para guardar configuracion e ingestar. Si una API local recibe `dashboard_id`, filtra por ese dashboard; si se omite, resuelve el default del pais. El modo de sesion por defecto es `controlled`, con perfil Playwright propio de la app. El modo
`browser` queda como compatibilidad legacy y se migra a `controlled` al leer configuracion.

## Offline

Home, Dashboards, Datasets y Analytics no importan modulos Quantum ni llaman URLs externas. El backend expone datos calculados desde Parquet.

La app local excluye videos de sesiones: no hay rutas `/video`, componentes de reproduccion, enlaces ni persistencia de URLs de video.
