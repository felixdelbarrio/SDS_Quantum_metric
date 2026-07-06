# Multi Dashboard Ingestion Storage

Ingestion resolves the default dashboard for the country at start time. Captured rows carry:

- `country`
- `dashboard_id`
- `dashboard_name`
- `dashboard_source`
- `team_id`
- `tab_name`
- `widget_id`
- `widget_type`
- `card_id`
- `visual_role`
- `range_key`
- `source_ts_start`
- `source_ts_end`
- `query_hash`
- `response_hash`

Raw calls dedupe by dashboard, card/widget, range and request/response hash. Derived datasets are written under `range_key=<range>/...` and expose dashboard/widget metadata for filtering.
