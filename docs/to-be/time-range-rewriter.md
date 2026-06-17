# Time Range Rewriter

## Responsabilidad

`backend/app/ingestion/time_rewriter.py` reescribe rangos temporales de payloads Quantum antes de capturar datos locales.

Soporta:

- `ts` top-level.
- Predicados anidados con `gte` y `lt`.
- Metadata `baseTs`, `startTs` y `endTs`.
- Epoch en segundos, epoch en milisegundos e ISO.

## Auditoria

La captura persiste rango origen, rango chunk, timezone, etiqueta de periodo y estado de reescritura junto a cada raw API call.
