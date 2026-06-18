# Contrato export/import

## ZIP

El ZIP exportado incluye:

```text
manifest.json
config/quantum.json
parquet/country=<pais>/...
```

## Seguridad

No se exportan cookies, Authorization, secrets ni tokens. La importacion rechaza rutas peligrosas, paths inesperados bajo `config/` y payloads de configuracion con campos que parezcan secretos.

## Importacion

La importacion valida `manifest.json`, upserta raw calls mediante merge deduplicado, copia entidades derivadas y restaura `config/quantum.json`.
