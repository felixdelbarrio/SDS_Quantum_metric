# Multi Dashboard Datasets

Cada captura/derivado/regresion incluye:

- `country`
- `dashboard_id`
- `dashboard_name`
- `widget_id`
- `card_id`
- `widget_type`
- `tab_name`
- `tab_index`
- `range_key`

Las APIs locales aceptan `dashboard_id`; si se omite, resuelven el default del pais.

Datasets muestra entidades agrupadas por dashboard cuando la metadata existe.

La ingesta captura solo el dashboard default configurado para el pais y solo widgets soportados/habilitados. Si no hay default o no hay widgets reales, la ingesta falla con mensaje accionable en lugar de usar mocks.
