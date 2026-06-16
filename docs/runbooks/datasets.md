# Datasets Runbook

## Auditoria

1. Abrir Datasets.
2. Elegir pais.
3. Usar `Auditar`.
4. Cambiar tabs de entidad para revisar RAW, contratos, derivados, chart payloads y regresion.

## Export

Usar `Exportar` por pais. El ZIP incluye Parquet y manifest. No incluye cookies ni secretos.

## Import

Usar `Importar` con ZIP generado por la aplicacion. El backend valida `manifest.json` y copia solo Parquet bajo `data/parquet`.

## Regenerar

`Regenerar derivados` reconstruye contratos visuales, snapshots, widgets, tablas, timeseries y chart payloads desde RAW.

## Borrar

El borrado requiere confirmacion API `confirm={country}` y modal en UI. Elimina RAW, derivados y regresion del pais.
