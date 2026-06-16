# Datasets Runbook

## Auditoria

1. Abrir Datasets.
2. Elegir pais.
3. Usar `Auditar`.
4. Cambiar tabs de entidad para revisar RAW, contratos, derivados, chart payloads y regresion.

La cabecera muestra la ruta persistente activa. Si se detecta `./data` legacy, migrar antes de borrar nada.

## Export

Usar `Exportar` por pais. El ZIP incluye Parquet y manifest. No incluye cookies ni secretos.

## Import

Usar `Importar` con ZIP generado por la aplicacion. El backend valida `manifest.json` y copia solo Parquet bajo la ruta persistente activa.

## Regenerar

`Regenerar derivados` reconstruye contratos visuales, snapshots, widgets, tablas, timeseries y chart payloads desde RAW.

## Borrar

El borrado requiere confirmacion API `confirm={country}` y modal en UI. Elimina RAW, derivados y regresion del pais.

La UI exige escribir exactamente el codigo de pais antes de habilitar el boton destructivo.
