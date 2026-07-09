# Ingestion Scope Locking

La ingesta bloquea duplicados por scope activo.

## Scope

El scope combina:

- pais;
- dashboard default resuelto;
- `range_key`;
- `start_date`;
- `end_date`;
- dias explicitos si aplica.

## Comportamiento

Si existe una ingesta no terminal para el mismo scope, `IngestionService.start()` lanza `IngestionAlreadyRunning`.

Los endpoints:

- `/api/ingestions`
- `/api/ingestions/missing-days`
- `/api/ingestions/range`

devuelven `409` con:

```json
{
  "code": "already_running",
  "ingestion_id": "<id-activo>"
}
```

Cuando el job termina, se cancela o falla, el scope se libera en `finally`.
