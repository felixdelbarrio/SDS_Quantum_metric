# Persistent Data Dir

## Politica

La ruta activa por defecto se calcula con `platformdirs.user_data_dir("SDS Quantum Metric", "SDS")`.

`QM_DATA_DIR` sigue existiendo como override explicito para desarrollo, pruebas o migraciones controladas.

## Migracion legacy

Si existe `./data` y no coincide con la ruta persistente, `/api/datasets` expone `legacy_data_detected=true`.

`POST /api/datasets/migrate-legacy-data` importa Parquet legacy a la ruta persistente sin crear datos nuevos ni sinteticos.

## UI

Datasets muestra la ruta local activa y exige confirmacion exacta del pais antes de borrar datos destructivamente.
