# Ingesta de dias faltantes

## Endpoints

```http
GET /api/local-dashboard/coverage?country=MX&start=2026-06-17&end=2026-06-18
POST /api/ingestions/missing-days
```

Payload:

```json
{
  "country": "MX",
  "days": ["2026-06-17"]
}
```

## Flujo

1. Dashboard cambia pais o rango.
2. Frontend consulta coverage.
3. Si `complete=false`, muestra una pildora discreta.
4. El usuario puede continuar con datos disponibles.
5. Si acepta, se lanza ingesta async con chunks diarios explicitos.
6. Al publicar datos se invalidan queries de dashboard e ingestas.

## Garantias

La ingesta de faltantes usa dias locales CST y no bloquea navegacion.
