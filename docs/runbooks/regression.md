# Runbook - Regression

## Iteración 18: criterio de aceptación

Comparar por widget valor/formato, comparación, tabla, chart type, series, ejes, bandas, leyenda,
sección/layout, periodo y timezone. Cualquier diferencia produce FAILED. Falta de autenticación,
contrato o evidencia produce BLOCKED, nunca PASSED. Guardar MD y JSON separados por país,
dashboard y `range_key`.

La regresion Web vs Local compara por:

- pais;
- `dashboard_id`;
- `widget_id`;
- `range_key`;
- rol visual.

Los reportes incluyen dashboard y widget en Parquet. Los markdown incluyen dashboard ID y nombre.

Para Iteracion 14 el reporte especifico de `last_7_days` se guarda como
`docs/regression/iteration-14-last-7-days-dashboard-<dashboard_id>.md` y `.json`.
Si Quantum Web redirige a login, el reporte debe quedar `BLOCKED`, nunca `PASSED`.

Para Iteracion 15:

- Colombia SDS escribe `docs/regression/iteration-15-co-sds-last-7-days.*`.
- Mexico default escribe `docs/regression/iteration-15-mx-default-last-7-days.*`.
- Si no hay sesion autenticada, usar estado `BLOCKED_AUTH`.

Para Iteracion 16:

- Colombia SDS escribe `docs/regression/iteration-16-co-sds-last-7-days.*` y debe quedar `PASSED` 11/11.
- Mexico default escribe `docs/regression/iteration-16-mx-default-last-7-days.*` y debe quedar `PASSED` 9/9.
- La regresion de widgets genericos compara valores, filas visibles, dimensiones y metricas normalizadas.

Para Iteracion 17:

- Colombia SDS escribe `docs/regression/iteration-17-co-sds-last-7-days.*` y debe quedar `PASSED` 11/11 con tabs `Overview general` y `Easy Dashboard Example`.
- Mexico default escribe `docs/regression/iteration-17-mx-default-last-7-days.*` y debe quedar `PASSED` 9/9 sin tabs duplicadas.
- Home debe consumir `/api/local-dashboard/dashboard`; los endpoints summary/errors son compatibilidad, no el contrato principal.
