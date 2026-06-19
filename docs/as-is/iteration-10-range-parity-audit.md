# Iteracion 10 - Auditoria as-is de paridad por rango

Fecha: 2026-06-19

## Alcance revisado

Se revisaron los flujos de ingesta, persistencia, derivacion, API local, UI, exportacion y sesion Quantum en:

- `backend/app/ingestion/service.py`, `planner.py`, `time_rewriter.py`, `policy.py`, `capture.py`
- `backend/app/quantum_dashboard/range_query.py`, `service.py`, `builder.py`, `parsers.py`, `regression.py`, `evidence.py`, `chart_axes.py`, `periods.py`
- `backend/app/storage/parquet_store.py`
- `backend/app/api/routes.py`
- `backend/app/quantum/config_store.py`, `schemas.py`
- `frontend/src/features/home/*`
- `frontend/src/features/datasets/DatasetsPage.tsx`
- `frontend/src/features/quantum-config/QuantumPage.tsx`
- `desktop/app.py`, `scripts/build_desktop.py`
- `backend/app/config/settings.py`, `paths.py`

## Hallazgos

1. **Today esta razonablemente preservado, pero no aislado por contrato.** La iteracion anterior dejo `Today` con regresion pasada en datos reales, pero los datasets derivados siguen escribiendose por pais y tipo de dataset, no por `range_key`. Esto permite que una captura posterior de Yesterday o Last 7 Days sustituya el dataset que Home interpreta como el rango activo.

2. **Los widgets de Errores usan los mismos parsers generales que Summary.** `errors.error_sessions_by_app_name_comparison` y `errors.error_session_percentage_by_app_name` ya tienen parsers dedicados, pero la regresion solo compara parcialmente tabla/donut y no deja evidencia por rango. Si el parser elige una respuesta de otro rango, el widget puede parecer listo sin ser equivalente a Web.

3. **Yesterday y Last 7 Days no tienen lectura local estricta por `range_key`.** La UI envia fechas a Summary/Errors/tablas, pero no envia `range_key`. El backend valida solo `_period_matches` contra el periodo agregado de los datasets actuales. No existe seleccion explicita de un contrato `today|yesterday|last_7_days`.

4. **La ingesta de dias faltantes puede terminar aunque el rango funcional siga mal.** `IngestionService` marca `completed` si no hay missing roles y la regresion general pasa. La regresion no recibe `range_key` ni valida cobertura/rango seleccionado. Por tanto, un backfill puede quedar “verde” con datos derivados de otro contrato.

5. **Existe riesgo real de mezcla de rangos.** `ParquetStore.merge_raw_calls` deduplica y elimina solapes por `source_ts_start/source_ts_end`, pero `build_derived_datasets` lee todos los raw calls del pais y selecciona la ultima llamada por rol con score. No filtra por `range_key`, `range_start`, `range_end` ni dashboard/rango activo.

6. **`period_start`, `period_end` y `range_key` estan incompletos.** Las filas derivadas tienen `period_start/end/timezone`, pero no `range_key`, `capture_mode`, `source_query_hash`, `source_response_hash` ni `web_snapshot_hash` canonicos. La API de coverage acepta `range_key`, pero los endpoints de datos no.

7. **Last 7 Days se reconstruye como captura diaria, no como contrato de rango probado.** El planner divide en chunks diarios. Si Quantum Web usa `/analytics/historical` con cuerpo especifico de rango, el almacenamiento actual no distingue entre respuesta diaria y respuesta de rango. Esto puede divergir en metricas no agregables.

8. **Las respuestas de rango pueden guardarse bajo particiones diarias incompatibles.** `_publish_daily_raw_calls` particiona por el dia de `source_ts_start`. Una query de rango multi-dia queda asociada al primer dia si no se anade metadata de rango.

9. **`chart_payload` puede corresponder a otro rango.** `timeseries_by_role` selecciona llamadas por score en todo el pais. No se comprueba que el payload elegido tenga el mismo periodo que el widget principal ni que coincida con el rango solicitado por UI.

10. **El warning de Today es menos agresivo que antes, pero aun insuficiente.** `range_query` ya usa `info` para Today parcial. Falta `data_quality`, `last_regression_status`, distincion `regression_failed` y mantener warning/error si la ingesta no pasa regresion.

11. **Exportar no cumple el contrato operativo.** `POST /api/datasets/export` devuelve un `FileResponse` y el frontend descarga un blob. No devuelve `status/path/filename/size_bytes`, no expone latest export, y escribe en `settings.exports_dir`, no en Descargas por defecto.

12. **No se observa acceso a Descargas al arrancar.** `Settings` crea `exports_dir` bajo datos de app, pero no toca `~/Downloads`. Al cambiar a Descargas debe mantenerse esta propiedad: no acceder hasta exportar o cambiar ruta.

13. **La sesion por defecto puede disparar el aviso de Chrome.** `Settings.qm_session_mode` y `QuantumConfig.session_mode` tienen default `browser`; `BrowserCookieProvider.load("chrome")` abre la DB SQLite del perfil real de Chrome y consulta Safe Storage. Este es el comportamiento asociado al aviso `chrome_unusual_artifacts_access_proc`.

14. **La reescritura temporal no valida estrictamente antes de persistir.** `apply_ingestion_range` reescribe y `capture.py` extrae rango de la request final, pero no aborta ni marca `failed` si el rango extraido no coincide con el chunk solicitado. Tampoco hay campos `requested_range_*`, `extracted_range_*` y `range_validation_status/error`.

## Conclusion

La causa estructural de los fallos no Today es que la aplicacion trata los derivados como “ultimo dashboard del pais” en lugar de “contrato exacto pais/dashboard/widget/rango”. La solucion debe aislar rangos en raw, derivados, regresion, evidencia y API; validar la reescritura temporal antes de persistir; y hacer que coverage/ingesta/export/configuracion informen estados accionables.
