# Iteracion 6 Code Audit

## Hallazgos

- El binario podia depender de rutas relativas (`data`, `frontend/dist`) y perder historico al ejecutarse fuera del repo.
- `make build` fallaba si el entorno desktop no tenia Pillow instalado para generar iconos.
- La ingesta larga no exponia progreso granular por ventana temporal y card obligatoria.
- Las respuestas Quantum con ventanas de tiempo embebidas no se reescribian siempre antes de capturar datos locales.
- Home podia quedar sin graficas utiles cuando faltaba `chart_payload`, pero el fallo no estaba clasificado como contrato roto.
- Datasets leia entidades completas para auditoria, lo que no escala con RAW grande.

## Restricciones confirmadas

- No se admiten datos mock en Home ni Datasets.
- La app local no implementa sesiones live ni reproduccion de video.
- Quantum Web solo se llama desde ingesta, discovery y regresion.
- Home consume Parquet derivado y contratos graficos persistidos.
