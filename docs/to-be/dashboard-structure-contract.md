# Dashboard Structure Contract

`QuantumDashboardStructure` agrupa tabs y widgets del dashboard seleccionado.

Tabs:

- `tab_id`
- `tab_index`
- `name`
- `normalized_role`

Widgets:

- `widget_id`
- `card_id`
- `title`
- `tab_name`
- `tab_index`
- `visual_role`
- `widget_type`: `chart`, `table`, `donut` o `unknown`
- `supported`
- `enabled`

Los widgets sin parser quedan visibles como no soportados y no se activan por defecto.
