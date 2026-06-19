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

Desde Iteracion 10, la ingesta iniciada desde Ingesta captura explicitamente `today` como
contrato de rango. Los botones de Home para Today, Yesterday y Last 7 Days llaman
`/api/ingestions/missing-days` con `range_key`, `start_date` y `end_date`; no se reutilizan
datos de otro rango.

## Incremental

- Sin datos locales: captura desde `hoy - depth_days` hasta hoy.
- Con datos: reingesta los dias definidos por `QUANTUM_INCREMENTAL_REPROCESS_DAYS`, por defecto hoy/ayer.
- No se recapturan historicos completos salvo que se borre el pais o se fuerce una nueva ventana.
- El rango se divide con `QUANTUM_INGESTION_CHUNK_DAYS`, por defecto chunks diarios para ventanas largas.
- Cada request Quantum se reescribe con el chunk activo antes de persistir RAW.
- Cada response capturada se valida contra el rango objetivo. Si el rango extraido no coincide,
  la response no se publica como dato valido.
- Si una tab obligatoria no emite responses `/analytics`, la ingesta falla de forma explicita.
  Nunca debe terminar `completed` con `raw_calls=0` para un chunk capturado.

## Validacion

1. Revisar Home para Summary y Errores.
2. Revisar Datasets para RAW, derivados, `chart_payloads` y regresion.
3. Abrir `docs/regression/latest-web-vs-local.md`.
4. Si una grafica aparece como fallo contractual, regenerar derivados o repetir ingesta antes de aceptar el resultado.

No hay reproduccion local de sesiones ni rutas de video.
# Ingesta diaria y faltantes

- La ingesta normal planifica chunks de un dia.
- `/api/ingestions/missing-days` acepta dias locales explicitos.
- El boton de un pais queda deshabilitado si ese pais ya tiene ingesta activa.
- La UI muestra una card solo para la ingesta activa y el historico en tabla.
- Al finalizar se actualizan particiones diarias y `day_coverage.parquet`.

# Iteracion 9

- La ingesta usa el dashboard default validado del pais.
- Si no hay dashboard validado, falla con mensaje accionable y no marca `completed`.
- Solo se persisten roles de widgets habilitados.
- Los widgets deshabilitados no se derivan ni entran en regresion.
- Los errores de ingesta guardan etapa, endpoint, chunk y rango sanitizados.

# Iteracion 10

- La sesion por defecto es `controlled`, sin leer perfiles reales de Chrome.
- Los rangos Today, Yesterday y Last 7 Days se persisten con `range_key`.
- Los derivados no agregables requieren contrato Quantum capturado para el rango completo.
- La ingesta falla si la reescritura temporal no puede validarse estrictamente.
