# Runbook - Ingestion

La ingesta usa solo el dashboard default del pais.

Antes de ingestar:

- El pais debe estar activo.
- Debe existir dashboard default validado.
- Debe haber widgets soportados y habilitados.

La ingesta persiste dashboard y widget en RAW, derivados y regresion.

Desde Iteracion 14, cada fila capturada incluye `dashboard_source`, `team_id`,
`widget_id`, `widget_type` y `visual_role` cuando Quantum los expone. Si el default
cambia, la nueva ingesta queda separada por pais, dashboard y widget.

Estados accionables de Iteracion 15:

- `failed_no_session`: falta sesion Quantum autenticada.
- `failed_dashboard_not_found`: no hay default validado o no se resuelve el dashboard.
- `failed_no_widgets`: no hay widgets soportados habilitados.
- `failed_no_analytics_responses`: Quantum no emitio analytics para las tabs configuradas.
- `cancelled_by_user`: cancelacion explicita del usuario.

Para rangos preset, la URL de captura incluye `ts=<range_key>`.
