# Manual Dashboard Validation

## Supported Input

Manual dashboards accept:

- full Quantum dashboard URL;
- raw dashboard ID.

For Colombia SDS:

- base_url: `https://bbvaco.quantummetric.com`
- dashboard_id: `fccfa9f6-5d01-47cf-9ba6-b7bccd4d4f2b`
- team_id: `24feba5b-307d-40ed-83de-478111f8938e`
- visible name: `SDS`
- range example: `last_7_days`

## Parser Contract

`parse_dashboard_url_or_id(value)` returns:

- `dashboard_id`
- `team_id`
- `base_url`
- `range_key`

When the value is a raw ID, only `dashboard_id` is required.

## Validation Contract

Validation calls Quantum Web dashboard structure discovery. A manual dashboard is persisted only when real tabs or widgets are recovered, or the route returns a clear error. Manual dashboards are written to both config and dashboard resource cache with source `manual`.

## Default Selection

Manual dashboards can be selected as the default for a country. If a manual dashboard ID already exists in API resources, local metadata is merged by ID instead of duplicating the dashboard.
