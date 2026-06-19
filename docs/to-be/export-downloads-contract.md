# Contrato de export a Downloads

## Objetivo

La exportacion debe generar un ZIP operativo en una ruta visible por el usuario, por defecto
`~/Downloads`, sin depender de descargas del navegador ni de blobs frontend.

## API

```http
POST /api/datasets/export
Content-Type: application/json

{"countries": ["MX"]}
```

Respuesta:

```json
{
  "status": "exported",
  "path": "/Users/user/Downloads/sds-quantum-metric-export-20260619-120000.zip",
  "filename": "sds-quantum-metric-export-20260619-120000.zip",
  "size_bytes": 1234
}
```

Si el payload no incluye `export_path`, el backend usa la ruta guardada en configuracion Quantum.
Si tampoco existe, usa `~/Downloads`.

## Contenido

```text
manifest.json
config/quantum.json
parquet/country=<pais>/...
reports/...
schemas/export_contract.json
```

## Seguridad

El ZIP no contiene cookies, tokens, cabeceras Authorization ni secretos. La UI muestra la ruta
creada por backend; no intenta simular una descarga browser.
