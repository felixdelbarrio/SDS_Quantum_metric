# Ingestion Runbook

## Configuracion

1. Abrir Quantum.
2. Seleccionar browser, sesion, pais activo y Base URL.
3. Definir `Profundidad de datos a ingestar` si se necesita algo distinto a 365 dias.
4. Guardar.

El descubrimiento de dashboard ocurre de forma automatica durante guardado o ingesta cuando hay metadata suficiente.

## Ejecucion

1. Abrir Ingesta.
2. Seleccionar pais.
3. Ejecutar `Ingestar`.
4. Seguir estado: `planning_range`, `planning_chunks`, `capturing_chunk`, `persisting_raw`, `building_derived`, `running_regression`.

La UI muestra chunks planificados/completados, rango temporal activo, llamadas, filas RAW, cards obligatorias, derivados, regresion y porcentaje.

## Incremental

- Sin datos locales: captura desde `hoy - depth_days` hasta hoy.
- Con datos: reingesta los dias definidos por `QUANTUM_INCREMENTAL_REPROCESS_DAYS`, por defecto hoy/ayer.
- No se recapturan historicos completos salvo que se borre el pais o se fuerce una nueva ventana.
- El rango se divide con `QUANTUM_INGESTION_CHUNK_DAYS`, por defecto chunks diarios para ventanas largas.
- Cada request Quantum se reescribe con el chunk activo antes de persistir RAW.

## Validacion

1. Revisar Home para Summary y Errores.
2. Revisar Datasets para RAW, derivados, `chart_payloads` y regresion.
3. Abrir `docs/regression/latest-web-vs-local.md`.
4. Si una grafica aparece como fallo contractual, regenerar derivados o repetir ingesta antes de aceptar el resultado.

No hay reproduccion local de sesiones ni rutas de video.
