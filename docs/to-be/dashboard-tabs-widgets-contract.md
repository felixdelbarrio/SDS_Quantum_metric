# Dashboard Tabs and Widgets Contract

## Endpoint

`POST /api/quantum/countries/{country}/dashboards/{dashboard_id}/structure/discover`

Lee la estructura real mediante GraphQL `LoadDashboard($dashboardId: ID!)`.

## Parsing

- `data.resource.entity.title` se guarda como `dashboard_name`.
- `data.resource.entity.tabs` se parsea como JSON.
- Cada tab conserva `id`, indice, nombre y rol normalizado.
- Los widgets se extraen de `layoutCardsMap`, ordenados por `layout` (`y`, `x`, orden original).
- Los bloques `component=Text` sin card no se guardan como widgets.
- `visualization=donut` gana sobre `type=CHART` para clasificar rosco/donut.

## Widget

Campos persistidos por widget:

- `widget_id`
- `card_id`
- `title`
- `tab_id`
- `tab_name`
- `tab_index`
- `visual_role`
- `widget_type`
- `enabled`
- `required`
- `supported`
- `source`
- `discovered_at`

Los widgets no soportados quedan visibles pero deshabilitados. No se activan por defecto.
