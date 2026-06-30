# Iteracion 11 - saneamiento final

## Cambios de producto

- Dashboard local no muestra Dimension ni Segmento.
- Los endpoints publicos `/api/analytics/dimensions` y `/api/analytics/segments` no se exponen.
- `/api/local-dashboard/*` no acepta `dimension`/`segment` ni devuelve `applied_dimension`/`applied_segment`.
- La etiqueta visible es `Profundidad por defecto`; el nombre interno `ingestion_depth_days` queda como schema estable.
- `Ingestar` en Ingesta usa `range_key=default` y la profundidad por defecto.
- `Ingestar periodo` en Home usa `/api/ingestions/range` con el rango visible.

## Contratos corregidos

- Modo barras renderiza `rect` reales, no paths de linea.
- `Delta Page Views`, `Delta Sessions` y `Delta Conversiones` se parsean desde Web/API cuando existen y se pintan con estado semantico.
- La tabla de resumen no crea jerarquias falsas. Solo hay chevron si Web entrega hijos reales.
- `% Sesiones con Error por App Name` se sirve por defecto en `row_index` ascendente, preservando orden Web capturado.
- Datasets separa `loading`, `error`, `loaded_empty` y `loaded_with_data`; no muestra falso vacio durante carga inicial.

## Robustez

- El fallback SPA devuelve 404 para rutas `/api/*` inexistentes, evitando que endpoints eliminados parezcan vivos.
- Las queries de Home incluyen `range_key` en cache key para no mezclar presets con mismas fechas.
- El servicio local elimina recalculos de segmento que anulaban chart payloads y podian degradar paridad.
