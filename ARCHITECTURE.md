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
- `capture.py`: captura guiada de tabs Resumen y Errores.
- `card_mapper.py`: asociacion de llamadas Quantum a roles visuales.
- `parsers.py`: estrategias por rol visual, con `chart_payload` cuando la respuesta trae puntos.
- `builder.py`: raw calls -> visual contracts -> web snapshots -> derived Parquet -> chart payloads.
- `service.py`: endpoints `/api/local-dashboard/*` desde derivados.
- `regression.py`: comparacion Web vs Local de valores, ejes, leyendas, series y tablas.
- `range_query.py`: resolucion de rangos y cobertura con severidad por preset.
- `evidence.py`: trazabilidad widget a widget desde Web snapshot hasta API local.

## Flujo de ingesta

1. El usuario lanza una ingesta desde la seccion Ingesta.
2. Se abre un contexto Playwright efimero con cookies en memoria.
3. Se resuelve dashboard/team/tabs internamente.
4. Se navega `Resumen` y `Errores`.
5. Se capturan respuestas reales de `/analytics` y `/analytics/historical`.
6. Se guardan raw calls normalizadas, particiones diarias y manifests en Parquet dentro de la ruta persistente.
7. Se generan contratos visuales, snapshots web, datasets derivados y `derived/chart_payloads`.
8. Se ejecuta regresion Web vs Local solo para widgets habilitados.
9. La ingesta solo termina `completed` si la regresion pasa.

La politica de rango usa `QUANTUM_INGESTION_DEPTH_DAYS`, `QUANTUM_INCREMENTAL_REPROCESS_DAYS` y `QUANTUM_INGESTION_CHUNK_DAYS`. El planner divide ventanas largas en chunks y el rewriter aplica el rango activo a payloads Quantum antes de persistir.

## Flujo del dashboard offline

1. Home llama `/api/local-dashboard/countries` para elegir pais por defecto.
2. El backend comprueba contratos, derivados, coverage diario y regresion.
3. Summary y Errors se sirven desde `derived/*`.
4. Search y sort operan sobre Parquet derivado local.
5. Si falta una card obligatoria, falla regresion o faltan dias, se devuelve error accionable.

## Contrato grafico

Las cards graficas no se renderizan desde agregados. Backend persiste `ChartPayload` con ejes, ticks, series, leyenda, bandas y periodo. Frontend pinta ese payload con SVG. Si falta el contrato, se muestra fallo contractual y regresion falla con estados especificos.

## Datasets Auditables

Datasets expone entidades Parquet por pais mediante `/api/datasets/{country}/entities` y `/api/datasets/{country}/entities/{entity}`. Las entidades incluyen categoria, dashboard ID y widget role. Las respuestas son paginadas; RAW completo solo se lee bajo demanda. Export/import incluye `config/quantum_config.json` y datos Parquet, rechazando secretos y rutas peligrosas. `/api/datasets/{country}/evidence` expone la cadena Web -> RAW -> derived -> API.

## Configuracion persistente

`backend/app/quantum/config_store.py` escribe `config/quantum_config.json` de forma atomica con schema version. El modelo contiene paises, dashboards, widgets, tema, browser, modo de sesion y profundidad de ingesta. Cookies y Authorization nunca se persisten.

## Offline

Home, Dashboards, Datasets y Analytics no importan modulos Quantum ni llaman URLs externas. El backend expone datos calculados desde Parquet.

La app local excluye videos de sesiones: no hay rutas `/video`, componentes de reproduccion, enlaces ni persistencia de URLs de video.
