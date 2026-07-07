# Runbook - Regression

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
