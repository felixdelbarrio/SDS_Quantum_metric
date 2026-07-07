# Dashboard Widget Tab Contract

## Source Of Truth

Dashboard structure comes from Quantum Web `LoadDashboard` GraphQL payloads. The preferred path is:

`data.resource.entity.tabs -> layoutCardsMap`

## Tab Fields

- `tab_id`
- `tab_index`
- `name`
- `normalized_role`

Known normalized roles:

- `summary`
- `errors`

Unknown real tabs keep their visible name and order.

## Widget Fields

- `widget_id`
- `card_id`
- `title`
- `tab_id`
- `tab_name`
- `tab_index`
- `widget_type`
- `visual_role`
- `enabled`
- `supported`

## Grouping Rules

1. Prefer exact `tab_id`.
2. Then match visible `tab_name`.
3. Then match normalized role.
4. Finally match `tab_index` only when the widget has no tab name.
5. Unassigned widgets render under `Sin pestana`.

Widgets must never be forced into `Resumen` when the tab cannot be determined.
