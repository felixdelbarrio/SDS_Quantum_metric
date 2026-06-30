# Range Ingestion States

## Botones

- Ingesta -> `Ingestar`: usa Profundidad por defecto y `range_key=default`.
- Home -> `Actualizar hoy`: usa `range_key=today` y las fechas visibles.
- Home -> `Ingestar periodo`: usa `range_key=yesterday`, `last_7_days` o `custom` y las fechas visibles.

## Endpoint

```http
POST /api/ingestions/range
```

```json
{
  "country": "MX",
  "range_key": "last_7_days",
  "start_date": "2026-06-24",
  "end_date": "2026-06-30",
  "reason": "missing_days"
}
```

## Estados de banner

- `complete`: sin banner.
- `missing_days`: warning con boton activo.
- `range_mismatch`: warning con boton activo.
- `regression_failed`: error con boton activo.
- `complete` con warning `none`: no muestra accion.

El boton solo queda deshabilitado mientras la mutacion esta en curso.
