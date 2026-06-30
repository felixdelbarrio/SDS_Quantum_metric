# Datasets Runbook

## Auditoria

1. Abrir Datasets.
2. Elegir pais.
3. Usar `Auditar`.
4. Cambiar tabs de entidad para revisar RAW, contratos, derivados, chart payloads y regresion.

La cabecera muestra la ruta persistente activa. Si se detecta `./data` legacy, migrar antes de borrar nada.
Durante la carga inicial debe mostrarse `Cargando datasets`; `Sin datos ingestados` solo es valido
cuando la respuesta termino y no hay datasets.

## Export

Usar `Exportar` por pais. El ZIP incluye Parquet y manifest. No incluye cookies ni secretos.

## Import

Usar `Importar` con ZIP generado por la aplicacion. El backend valida `manifest.json` y copia solo Parquet bajo la ruta persistente activa.

## Regenerar

`Regenerar derivados` reconstruye contratos visuales, snapshots, widgets, tablas, timeseries y chart payloads desde RAW.

## Borrar

El borrado requiere confirmacion API `confirm={country}` y modal en UI. Elimina RAW, derivados y regresion del pais.

La UI exige escribir exactamente el codigo de pais antes de habilitar el boton destructivo.
# Datasets Iteracion 8

- Datasets no ejecuta acciones tecnicas de regeneracion/regresion desde UI.
- La pantalla muestra ruta local, paises, estado compacto, import/export, borrar y entidades.
- Cada entidad usa paginacion backend y cabeceras fijas.
- El boton CSV exporta la entidad visible.
- Export ZIP incluye `config/quantum.json` y Parquet.
- Import rechaza rutas peligrosas y secretos.

# Iteracion 9

- Export ZIP incluye `config/quantum_config.json`.
- Entidades se agrupan por categoria, dashboard ID y widget role.
- `GET /api/datasets/{country}/evidence` muestra trazabilidad Web -> RAW -> derived -> API.
- Import acepta ZIPs antiguos con `config/quantum.json`, pero escribe la ruta nueva.

# Iteracion 11

- Datasets separa estados `loading`, `error`, `loaded_empty` y `loaded_with_data`.
- Las entidades y filas muestran estados de carga propios para no confundir una espera con ausencia de datos.
- Los rangos se distinguen por `range_key`: `default`, `today`, `yesterday`, `last_7_days` y `custom`.
