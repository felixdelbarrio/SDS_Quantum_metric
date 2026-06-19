# Export/import Runbook

## Exportar

1. Abrir Datasets.
2. Seleccionar el pais.
3. Pulsar Exportar.
4. Confirmar la card `Export creado` con filename, tamano y ruta absoluta.
5. Verificar que el ZIP existe en la ruta configurada, por defecto `~/Downloads`.

## Validar ZIP

```bash
unzip -l ~/Downloads/sds-quantum-metric-export-*.zip
```

El ZIP debe contener `manifest.json`, `config/quantum.json`, `parquet/`, `reports/` y `schemas/`.
No debe contener cookies, tokens, Authorization ni perfiles de navegador.

## Importar

La importacion acepta solo archivos ZIP generados por esta app. Rechaza rutas peligrosas,
configuracion con secretos y entradas fuera del contrato.

## Diagnostico

Si la UI no muestra el ZIP creado:

1. Comprobar `GET /api/datasets/exports/latest`.
2. Revisar permisos de escritura de la ruta de export.
3. Repetir la exportacion con un `export_path` explicito.
