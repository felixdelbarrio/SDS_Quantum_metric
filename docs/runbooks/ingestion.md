# Ingestion Runbook

1. Abrir sesion en Chrome en `https://bbvamx.quantummetric.com`.
2. Abrir la app local con `make run`.
3. Ir a Quantum, validar la fila del pais con `base_url`, `dashboard_id`, `team_id` y `tab`.
4. Ejecutar Test de conexion.
5. Ir a Ingesta, seleccionar pais configurado y ejecutar Nueva ingesta.
6. Revisar progreso y manifest.
7. Verificar datos en Datasets.
8. Ir a Home y confirmar `Dashboard General {pais}`.
9. Revisar que el selector contiene solo paises con datos ingestados.
10. Validar pestaña Resumen:
   - widgets de paginas vistas, sesiones, conversion y tiempo medio;
   - tabla por App Name y sistema operativo;
   - search y ordenacion.
11. Validar pestaña Errores:
    - comparativa de sesiones con error;
    - porcentaje de sesiones con error;
    - search y ordenacion.
12. Abrir `Add Dashboard Dimension`, aplicar una dimension y confirmar que widgets y tablas se
    refrescan desde `/api/analytics/*`.
13. Abrir `Dashboard Segment`, aplicar un segmento y confirmar que widgets y tablas se filtran.

## Verificacion offline

1. Ejecutar una ingesta real.
2. Desconectar internet o bloquear el dominio Quantum.
3. Recargar Home.
4. Confirmar que el dashboard sigue funcionando sobre Parquet local.
5. Mover temporalmente `data/parquet/country=<pais>/raw_api_calls`.
6. Recargar Home y confirmar estado `empty` sin datos falsos.

## Seguridad

- Cookies y secretos no se persisten.
- Analytics offline no usa `QuantumClient`, Playwright ni `httpx`.
- Solo Test de conexion e Ingesta pueden llamar a Quantum.
