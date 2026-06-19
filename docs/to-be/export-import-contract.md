# Contrato export/import

## ZIP

El backend crea el ZIP en la ruta configurada por el usuario, por defecto `~/Downloads`. La
respuesta de `/api/datasets/export` es JSON con ruta absoluta, filename y tamano; el frontend no
genera blobs ni fuerza una descarga browser.

El ZIP exportado incluye:

```text
manifest.json
config/quantum.json
parquet/country=<pais>/...
reports/...
schema/dataset_schema.json
```

## Seguridad

No se exportan cookies, Authorization, secrets ni tokens. La importacion rechaza rutas peligrosas, paths inesperados bajo `config/` y payloads de configuracion con campos que parezcan secretos.

## Importacion

La importacion valida `manifest.json`, upserta raw calls mediante merge deduplicado, copia entidades derivadas y restaura `config/quantum.json`.
