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
