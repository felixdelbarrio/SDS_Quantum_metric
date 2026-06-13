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

## Flujo de conexion

1. El usuario abre Quantum > Test de conexion.
2. El backend lee la configuracion no sensible.
3. La cookie se obtiene en memoria desde navegador o modo manual.
4. Se llama `GET /data/init`, `GET /auth-token` y `POST /query`.
5. Se devuelve estado OK/KO con error sanitizado.

## Flujo de ingesta

1. El usuario lanza una ingesta desde la seccion Ingesta.
2. Se abre un contexto Playwright efimero con cookies en memoria.
3. Se navega el dashboard configurado.
4. Se capturan respuestas reales de `/analytics` y `/analytics/historical`.
5. Se guardan raw calls y manifests en Parquet particionado por pais.
6. Las vistas offline leen de APIs locales.

## Flujo del dashboard offline

1. Home llama `/api/analytics/countries` para elegir pais por defecto.
2. El backend lee raw calls Parquet del pais seleccionado.
3. `normalizer.py` extrae dimensiones, metricas, periodos y metadatos desde JSON local.
4. `query_engine.py` aplica segmento, dimension, search y sort.
5. Se devuelven widgets Resumen, tabla por App Name/Sistema operativo y vistas de Errores.
6. Si falta un campo fuente, el resultado se marca como empty o `null`; no se sintetizan datos.

## Offline

Home, Dashboards, Datasets y Analytics no importan modulos Quantum ni llaman URLs externas. El backend expone datos calculados desde Parquet.
