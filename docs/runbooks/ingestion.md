# Ingestion Runbook

1. Abrir sesion en Chrome en `https://bbvamx.quantummetric.com`.
2. Abrir la app local con `make run`.
3. Ir a Quantum, validar Browser, modo de sesion, pais activo y Base URL.
4. Ejecutar Test de conexion.
5. Ejecutar `Descubrir dashboard` y `Validar acceso`.
6. Ir a Ingesta, seleccionar pais configurado y ejecutar Nueva ingesta.
7. Revisar estados: `capturing_web`, `persisting_raw`, `building_derived_datasets`, `running_regression`.
8. Confirmar cards capturadas, obligatorias, derivados y regresion.
9. Verificar datos en Datasets.
10. Ir a Home y confirmar `Dashboard General {pais}`.
11. Revisar que el selector contiene solo paises con datos ingestados.
12. Validar pestaña Resumen:
   - widgets de paginas vistas, sesiones, conversion y tiempo medio;
   - tabla por App Name y sistema operativo;
   - search y ordenacion.
13. Validar pestaña Errores:
    - evolutivo de porcentaje de sesiones con error;
    - top 10 errores por nombre;
    - comparativa de sesiones con error por App Name;
    - porcentaje de sesiones con error por App Name;
    - search y ordenacion.
14. Abrir `docs/regression/latest-web-vs-local.md` y confirmar veredicto `PASSED` o `PASSED_WITH_TOLERANCE`.

## Verificacion offline

1. Ejecutar una ingesta real.
2. Desconectar internet o bloquear el dominio Quantum.
3. Recargar Home.
4. Confirmar que el dashboard sigue funcionando sobre Parquet local.
5. Recargar Home y confirmar estado derivado desde `/api/local-dashboard/*`.
6. Mover temporalmente `data/parquet/country=<pais>/derived`.
7. Recargar Home y confirmar error accionable sin datos falsos.

## Seguridad

- Cookies y secretos no se persisten.
- Local dashboard offline no usa `QuantumClient`, Playwright ni `httpx`.
- Solo Test de conexion e Ingesta pueden llamar a Quantum.
