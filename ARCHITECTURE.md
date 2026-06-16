# Architecture

## Componentes

- `backend`: FastAPI, Pydantic v2, cliente Quantum aislado, orquestador de ingesta, almacenamiento Parquet y analitica local.
- `frontend`: React + TypeScript + Vite, TanStack Query, Zustand, React Router y sistema de diseno centralizado.
- `desktop`: PyWebView para dar experiencia integrada.
- `data`: Parquet, manifests, catalogo y exports.

## Analitica local

La capa `backend/app/analytics` centraliza el dashboard offline:

- `models.py`: contratos Pydantic de paises, widgets, tablas, dimensiones, segmentos y estados vacios.
- `query_engine.py`: lectura de Parquet, filtrado, ordenacion y agregaciones.
- `normalizer.py`: parseo tolerante de `request_json` y `response_json`.
- `dimensions.py`: agrupacion de dimensiones inferidas.
- `segments.py`: segmentos aplicables desde valores locales.
- `errors.py`: calculo compartido de sesiones con error y porcentaje.

El motor lee solo `data/parquet/country=<pais>/raw_api_calls/*.parquet`. No usa
`QuantumClient`, Playwright ni clientes HTTP externos.

## Dashboard Quantum por cards

`backend/app/quantum_dashboard` implementa la capa de Iteracion 4:

- `catalog.py`: catalogo obligatorio de nueve roles visuales para Resumen y Errores.
- `discovery.py`: resolucion interna de dashboard, team y tabs desde `.env`, config o URL.
- `capture.py`: captura guiada de tabs Resumen y Errores.
- `card_mapper.py`: asociacion de llamadas Quantum a roles visuales.
- `parsers.py`: estrategias por tipo de card, con errores accionables.
- `builder.py`: raw calls -> visual contracts -> web snapshots -> derived Parquet.
- `service.py`: endpoints `/api/local-dashboard/*` desde derivados.
- `regression.py`: comparacion Web vs Local y reporte Markdown/JSON.

## Flujo de conexion

1. El usuario abre Quantum > Test de conexion.
2. El backend lee la configuracion no sensible.
3. La cookie se obtiene en memoria desde navegador o modo manual.
4. Se llama `GET /data/init`, `GET /auth-token` y `POST /query`.
5. Se devuelve estado OK/KO con error sanitizado.

## Flujo de ingesta

1. El usuario lanza una ingesta desde la seccion Ingesta.
2. Se abre un contexto Playwright efimero con cookies en memoria.
3. Se resuelve dashboard/team/tabs internamente.
4. Se navega `Resumen` y `Errores`.
5. Se capturan respuestas reales de `/analytics` y `/analytics/historical`.
6. Se guardan raw calls y manifests en Parquet particionado por pais.
7. Se generan contratos visuales, snapshots web y datasets derivados.
8. Se ejecuta regresion Web vs Local.
9. La ingesta solo termina `completed` si la regresion pasa.

## Flujo del dashboard offline

1. Home llama `/api/local-dashboard/countries` para elegir pais por defecto.
2. El backend comprueba contratos, derivados y regresion.
3. Summary y Errors se sirven desde `derived/*`.
4. Search y sort operan sobre Parquet derivado local.
5. Si falta una card obligatoria o falla regresion, se devuelve error accionable.

## Offline

Home, Dashboards, Datasets y Analytics no importan modulos Quantum ni llaman URLs externas. El backend expone datos calculados desde Parquet.
