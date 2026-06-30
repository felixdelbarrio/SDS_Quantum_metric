# Ingesta de periodo desde Home

## Endpoints

```http
GET /api/local-dashboard/coverage?country=MX&start=2026-06-17&end=2026-06-18
POST /api/ingestions/range
```

Payload:

```json
{
  "country": "MX",
  "range_key": "last_7_days",
  "start_date": "2026-06-24",
  "end_date": "2026-06-30",
  "reason": "missing_days"
}
```

## Flujo

1. Dashboard cambia pais o rango.
2. Frontend consulta coverage.
3. Si `warning_level` no es `none`, muestra una pildora discreta.
4. El usuario puede continuar con datos disponibles.
5. Si acepta, se lanza ingesta async del periodo visible completo.
6. Al publicar datos se invalidan queries de dashboard e ingestas.

## Garantias

La ingesta de periodo usa dias locales CST, conserva `range_key` y no bloquea navegacion.
