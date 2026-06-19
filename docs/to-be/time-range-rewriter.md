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

## Validacion estricta

Despues de reescribir, `validate_query_time_range` extrae el rango del payload final y lo compara
con el chunk objetivo con tolerancia maxima de un segundo. Si no se puede extraer rango, o si la
ventana difiere, la captura marca la response como invalida y la ingesta falla.

Los predicados soportan tanto `path` top-level como `arguments[0].path`, formato habitual en
queries Quantum con filtros anidados.
