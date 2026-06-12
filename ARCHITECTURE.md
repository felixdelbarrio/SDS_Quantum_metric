# Architecture

## Componentes

- `backend`: FastAPI, Pydantic v2, cliente Quantum aislado, orquestador de ingesta, almacenamiento Parquet y analitica local.
- `frontend`: React + TypeScript + Vite, TanStack Query, Zustand, React Router y sistema de diseno centralizado.
- `desktop`: PyWebView para dar experiencia integrada.
- `data`: Parquet, manifests, catalogo y exports.

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

## Offline

Home, Dashboards, Datasets y Analytics no importan modulos Quantum ni llaman URLs externas. El backend expone datos calculados desde Parquet.
