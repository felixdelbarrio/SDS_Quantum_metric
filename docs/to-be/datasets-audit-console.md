# Datasets Audit Console

## Entidades

Datasets lista entidades Parquet por pais desde el store central:

- RAW calls
- contratos visuales
- snapshots web
- derivados
- chart payloads
- regresion

## Lectura

Las entidades se consultan paginadas con lazy scan de Polars. La UI no carga RAW completo para mostrar una tabla de auditoria.

## Operaciones

Export, import, regeneracion de derivados, regresion y borrado usan los endpoints locales. El borrado exige confirmacion exacta en UI y API.
