# Ingestion Progress

## Estados

La ingesta publica progreso persistido con:

- `planning_range`
- `planning_chunks`
- `capturing_chunk`
- `persisting_raw`
- `building_derived`
- `running_regression`
- `completed`
- `failed_regression`
- `failed`

## Campos de progreso

Cada job conserva chunks planificados y completados, rango del chunk actual, llamadas capturadas, filas RAW, cards obligatorias, derivados, estado de regresion, mensaje y porcentaje.

La UI de Ingesta muestra estos datos como tarjetas de progreso y permite cancelar jobs activos.
