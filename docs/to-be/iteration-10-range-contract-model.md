# Iteracion 10 - Modelo de contrato por rango

## Objetivo

La app local debe servir Today, Yesterday y Last 7 Days desde datos Parquet capturados para
ese mismo rango. Un dato capturado para `today` no puede satisfacer `yesterday` ni
`last_7_days`.

## Campos canonicos

Cada raw API call persistida incluye:

- `range_key`: preset local solicitado (`today`, `yesterday`, `last_7_days`).
- `range_start`: inicio UTC solicitado.
- `range_end`: fin UTC solicitado.
- `range_timezone`: timezone operativo de Quantum.
- `capture_mode`: modo de captura (`range_contract` para rangos explicitos).
- `requested_range_start` y `requested_range_end`: rango que se intento reescribir.
- `extracted_range_start` y `extracted_range_end`: rango extraido tras reescritura.
- `range_validation_status`: `passed` o `failed`.
- `range_validation_error`: motivo tecnico si no se pudo validar.

Los derivados, snapshots web, contratos visuales, chart payloads y resultados de regresion
propagan `range_key`, `range_start`, `range_end`, `range_timezone`, `quantum_endpoint` y hashes
de evidencia.

## Particiones

Los datasets derivados por rango se escriben en:

```text
parquet/country=<pais>/range_key=<range>/derived/...
parquet/country=<pais>/range_key=<range>/regression/...
```

Para compatibilidad operativa, `today` tambien se publica en las rutas historicas sin
`range_key`. Las consultas nuevas siempre prefieren la ruta con rango cuando se solicita un
preset explicito.

## Reglas de lectura

- Home llama `/api/local-dashboard/*?range_key=<preset>`.
- Datasets expone las entidades Parquet sin fabricar datos de UI.
- El estado de cobertura distingue `complete`, `partial`, `empty` y `failed`.
- Un rango no pasa si faltan raw calls, derivados, chart payloads, cards obligatorias o regresion.

## Fallos bloqueantes

La ingesta falla y no publica datos locales como validos si:

- una respuesta Quantum no contiene rango extraible;
- el rango extraido difiere del rango solicitado por mas de un segundo;
- el parser no encuentra una card obligatoria habilitada;
- la regresion Web vs Local no pasa para el rango capturado.

