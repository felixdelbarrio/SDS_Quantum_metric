# Iteracion 6 Fix Design

## Objetivo

Cerrar la brecha entre la app local empaquetada y Quantum Web sin depender del directorio del repositorio, manteniendo datos reales auditables y fallando de forma explicita si falta contrato grafico.

## Cambios estructurales

- Rutas de datos y logs resueltas con `platformdirs`.
- Frontend servido desde `frontend_dist_path`, compatible con PyInstaller.
- Smoke test desktop antes y despues del empaquetado.
- Ingesta planificada en chunks diarios con progreso persistido.
- Reescritura centralizada de rangos temporales en payloads Quantum.
- Regresion estricta para payloads graficos, periodo, ejes, leyenda y series.
- Datasets auditables con lectura paginada de entidades Parquet.

## Criterio de aceptacion

`make CI` y `make build` deben quedar verdes. El binario debe servir `/api/health` y `/` sin requerir Vite ni rutas del repo.
