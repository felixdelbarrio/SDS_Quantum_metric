# Ingestion Capture Hardening

## Navigation

Ingestion dashboard URLs include:

- base URL;
- dashboard ID;
- `teamID` when available;
- tab index;
- `ts=<range_key>` when a preset range is selected.

## Capture

The browser capture listens to:

- `/analytics`
- `/analytics/historical`

Dashboard and widget metadata is discovered separately through GraphQL dashboard structure loading.

## No-Analytics Handling

Capture no longer fails on the first empty tab. It records tab failures, continues through the configured tabs, and raises only when every configured tab returns no analytics responses.

## Job Statuses

Actionable statuses:

- `failed_no_session`
- `failed_dashboard_not_found`
- `failed_no_widgets`
- `failed_no_analytics_responses`
- `failed_regression`
- `cancelled_by_user`

## Diagnostics

Failed jobs include country, dashboard, range, endpoint and chunk context in `job.details` where available.
