# Offline Analytics

Las APIs locales leen Parquet:

- `GET /api/datasets`
- `GET /api/dashboards`
- `GET /api/cards/{card_id}/data`
- `GET /api/analytics/countries`
- `GET /api/analytics/dashboard/summary`
- `GET /api/analytics/dashboard/summary/table`
- `GET /api/analytics/dashboard/errors`
- `GET /api/analytics/dashboard/errors/table`
- `GET /api/analytics/dimensions`
- `GET /api/analytics/segments`

El frontend no llama dominios Quantum en Home, Dashboards, Datasets o Analytics.

## Paises

`/api/analytics/countries` lista solo `ES`, `MX`, `PE`, `CO` y `AR`. Un pais tiene datos si
existe al menos una raw call Parquet bajo `country=<pais>/raw_api_calls`. El default es el
primer pais configurado con datos; si ninguno tiene datos, se usa el pais configurado o `MX`.

## Resumen

`/api/analytics/dashboard/summary` devuelve cuatro widgets:

- Paginas vistas: suma de `page_views`.
- Sesiones: suma de `sessions`.
- Sesiones con conversion: suma de `converted_sessions`.
- Tiempo medio de sesion: media ponderada por `sessions` cuando ambas metricas existen; si no,
  media simple de `avg_session_time`.

Cada widget puede incluir breakdown por dimension activa. Sin dimension activa se intenta
desglosar por `application_type`, `device_type` o `platform`. La serie temporal agrupa por
`source_ts_start` o `ingestion_ts`. La comparacion historica solo se muestra si existe un campo
delta en Parquet.

## Tabla Resumen

`/api/analytics/dashboard/summary/table` agrupa por `app_name` y `operating_system`. Si hay una
dimension activa, el nombre de fila usa esa dimension y mantiene `operating_system` cuando existe.
La API aplica `search`, `sort` y `direction`; el frontend no recalcula metricas.

Columnas principales:

- `name`
- `app_name`
- `operating_system`
- `page_views`
- `sessions`
- `conversions`
- deltas historicos si existen

## Errores

`/api/analytics/dashboard/errors` y `/errors/table` calculan:

- sesiones con error por App Name o dimension activa;
- porcentaje de sesiones con error por App Name o dimension activa.

El porcentaje se calcula como `sessions_with_error / sessions * 100` cuando ambas metricas
existen. Si no hay sesiones pero si hay `error_session_percent`, se usa ese valor fuente. Si no
hay ninguna metrica de error, la respuesta es `status: "empty"`.

## Dimensiones y segmentos

Las dimensiones se infieren desde:

- `request_json.dimensions.dimensions`
- `request_json.dimensionFills.dimensionFills`
- `request_json.metadata`
- claves no numericas de `response_json.rows`

Los segmentos se infieren desde valores reales de:

- plataforma;
- app name;
- browser;
- application type;
- operating system;
- filas con/sin error;
- filas con/sin conversion.

Aplicar una dimension o segmento altera las queries locales de widgets y tablas. No es solo UI.

## Estados vacios

Si no hay Parquet, raw calls, rows parseables o campos suficientes, las APIs devuelven
`status: "empty"`, `reason`, `required_dataset`, `available_datasets` y arrays vacios. La UI
muestra ese estado y no renderiza datos de ejemplo.

## Prueba offline

1. Ejecutar una ingesta.
2. Confirmar que existen archivos en `data/parquet/country=<pais>/raw_api_calls/`.
3. Desconectar internet o bloquear el dominio Quantum.
4. Recargar Home.
5. Verificar que `Dashboard General {pais}` sigue cargando desde `/api/analytics/*`.
6. Mover temporalmente `data/parquet` y recargar: debe aparecer estado vacio honesto.
